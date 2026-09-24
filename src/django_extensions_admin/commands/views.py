"""The admin pages: the commands a user may run, the launch form, and one run's result.

Rendering a Run control is a hint. Each view checks the registration and the permission
itself, and the worker checks both again.
"""

from __future__ import annotations

import json
import logging

from django.contrib import messages
from django.contrib.admin import helpers
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import connections, transaction
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from ..conf import get_setting
from . import registry
from .backend import CommandsUnavailable, get_backend, tasks_api

__all__ = ["urls"]

logger = logging.getLogger("django_extensions_admin.commands")

#: Signs the result reference. Specific to this use, so no other signed value fits.
RESULT_SALT = "django_extensions_admin.commands.result"
#: Seconds between automatic reloads of a pending result page (no JavaScript involved).
REFRESH_SECONDS = 3

STATES = {
    "READY": "queued",
    "RUNNING": "running",
    "SUCCESSFUL": "succeeded",
    "FAILED": "failed",
}
LABELS = {
    "queued": gettext_lazy("Queued"),
    "running": gettext_lazy("Running"),
    "succeeded": gettext_lazy("Succeeded"),
    "failed": gettext_lazy("Failed"),
    "unavailable": gettext_lazy("Unavailable"),
}


def urls(site):
    """URL patterns for *site*'s command pages, for ``path("admin/commands/", ...)``.

    Nothing is routed until a project includes this. Place it before ``site.urls``,
    whose last pattern catches every other path.
    """
    views = CommandViews(site)
    launch = site.admin_view(views.launch)
    # The launch view writes no application data, and it can only return a reference
    # once the task exists. ATOMIC_REQUESTS would hold the enqueue until the response
    # is complete, so opt out of it for every Django *database* alias (not the Tasks
    # alias). The handler looks for this on the callable the URL resolves to.
    for db_alias in connections.settings:
        launch = transaction.non_atomic_requests(using=db_alias)(launch)
    patterns = [
        path("", site.admin_view(views.index), name="index"),
        path("results/<str:token>/", site.admin_view(views.result), name="result"),
        path("<str:name>/", launch, name="launch"),
    ]
    return patterns, "admin_ext_commands", views.namespace


def open_transaction() -> bool:
    """True when any database connection is inside ``atomic()``.

    A connection that was never used in this thread cannot hold a transaction, so the
    initialized ones cover every database a backend could write its task to.
    """
    return any(conn.in_atomic_block for conn in connections.all(initialized_only=True))


class CommandViews:
    def __init__(self, site):
        self.site = site
        self.namespace = f"{site.name}_commands"

    # --- helpers -------------------------------------------------------------

    def url(self, name, *args):
        return reverse(f"{self.namespace}:{name}", args=args)

    def render(self, request, template, context, status=200):
        request.current_app = self.site.name
        context = {**self.site.each_context(request), "index_url": self.url("index"), **context}
        return TemplateResponse(
            request, f"django_extensions_admin/commands/{template}", context, status=status
        )

    def allowed(self, request, name):
        registration = registry.get(name)
        if registration is None:
            raise Http404(_("No such admin command."))
        if not registration.has_permission(request.user):
            raise PermissionDenied
        return registration

    @staticmethod
    def unavailable():
        try:
            get_backend()
        except CommandsUnavailable as exc:
            return str(exc)
        return None

    # --- index ---------------------------------------------------------------

    def index(self, request):
        commands = [
            {"registration": registration, "url": self.url("launch", registration.name)}
            for registration in registry.registrations()
            if registration.has_permission(request.user)
        ]
        context = {
            "title": _("Management commands"),
            "commands": commands,
            "unavailable": self.unavailable(),
        }
        return self.render(request, "index.html", context)

    # --- launch --------------------------------------------------------------

    def launch(self, request, name):
        registration = self.allowed(request, name)
        if request.method not in ("GET", "POST"):
            return HttpResponseNotAllowed(["GET", "POST"])
        unavailable = self.unavailable()
        status = 200
        if request.method == "GET":
            form = registration.form()
        else:
            form = registration.form(data=request.POST)
            if unavailable:
                messages.error(request, _("Nothing was queued: %s") % unavailable)
                status = 503
            elif form.is_valid():
                try:
                    payload = registry.build_payload(form)
                except registry.PayloadError as exc:
                    form.add_error(None, _("These values cannot be sent to a worker: %s") % exc)
                else:
                    response = self.dispatch(request, registration, payload)
                    if response is not None:
                        return response
                    status = 503
        return self.render(
            request, "launch.html", self.launch_context(registration, form, unavailable), status
        )

    def launch_context(self, registration, form, unavailable):
        command_help = ""
        try:
            command_help = registration.load_command().help
        except KeyError:
            pass  # the system check reports an unknown command
        fields = list(form.fields)
        return {
            "title": registration.description,
            "registration": registration,
            "command_help": command_help,
            "form": form,
            "adminform": helpers.AdminForm(form, [(None, {"fields": fields})], {})
            if fields
            else None,
            "errors": form.errors,
            "unavailable": unavailable,
            "media": form.media,
        }

    def dispatch(self, request, registration, payload):
        """Queue the run and redirect to its result, or say why it may not be queued."""
        if open_transaction():
            messages.error(
                request,
                _(
                    "Nothing was queued: this request is inside an open database transaction, "
                    "so the run could only start after the response and no result could be "
                    "shown. Launch commands from a request without a surrounding transaction."
                ),
            )
            return None
        backend = get_backend()
        from .tasks import enqueue_on_commit

        try:
            # A string: task arguments must be JSON, and a UUID or other non-integer
            # primary key is not. The worker's pk lookup and the reference accept it.
            actor_id = str(request.user.pk)
            result = enqueue_on_commit(registration.name, payload, actor_id, backend.alias)
        except Exception as exc:
            logger.exception("Could not queue admin command %r", registration.name)
            # The backend may have stored the run before failing (django-tasks-db inserts
            # the row, then sends task_enqueued); a stored run still executes. Say so,
            # rather than invite a second run of a command that may not be idempotent.
            messages.error(
                request,
                _(
                    "The run may not have been queued: the task backend raised %s. If it "
                    "was stored before the error, a worker will still run it, so check "
                    "before running the command again."
                )
                % type(exc).__name__,
            )
            return None
        if result is None:  # pragma: no cover - open_transaction() rules this out
            raise RuntimeError("The run was deferred to a transaction commit.")
        token = signing.dumps(
            {
                "id": str(result.id),
                "b": backend.alias,
                "c": registration.name,
                "u": str(request.user.pk),
            },
            salt=RESULT_SALT,
            compress=True,
        )
        messages.success(request, _("Queued “%s”.") % registration.description)
        return HttpResponseRedirect(self.url("result", token))

    # --- result --------------------------------------------------------------

    def result(self, request, token):
        try:
            reference = signing.loads(token, salt=RESULT_SALT)
        except signing.BadSignature:
            raise Http404(_("No such run.")) from None
        # A reference is its initiator's alone; to anyone else it does not exist.
        if not isinstance(reference, dict) or reference.get("u") != str(request.user.pk):
            raise Http404(_("No such run."))
        registration = self.allowed(request, reference.get("c"))
        context = {
            "title": registration.description,
            "registration": registration,
            "launch_url": self.url("launch", registration.name),
            **self.read_result(reference, registration),
        }
        context["state_label"] = LABELS[context["state"]]
        return self.render(request, "result.html", context, context.pop("status", 200))

    def read_result(self, reference, registration) -> dict:
        try:
            backend = get_backend()
        except CommandsUnavailable as exc:
            return {"state": "unavailable", "reason": str(exc), "status": 503}
        if reference.get("b") != backend.alias:
            return self.gone(
                _(
                    "The run was queued on the Tasks backend %(old)r, which is no longer the "
                    "one configured."
                )
                % {"old": reference.get("b")}
            )
        api = tasks_api()
        try:
            result = backend.get_result(reference["id"])
        except api.TaskResultDoesNotExist:
            return self.gone(_("The result is no longer available: it was pruned or is unknown."))
        except Exception:
            logger.exception("Could not read the result of admin command %r", registration.name)
            return {
                "state": "unavailable",
                "reason": _("The result could not be read right now."),
                "status": 503,
            }
        kwargs = result.kwargs or {}
        if (
            result.backend != backend.alias
            or kwargs.get("key") != registration.name
            or str(kwargs.get("actor_id")) != reference["u"]
        ):
            logger.warning("A signed reference does not match its stored run %s", result.id)
            return self.gone(_("The result is no longer available."))

        state = STATES.get(str(result.status), "unavailable")
        context = {
            "state": state,
            "enqueued_at": result.enqueued_at,
            "started_at": result.started_at,
            "finished_at": result.finished_at,
        }
        if state == "succeeded":
            context.update(self.output(result.return_value))
        elif state == "failed":
            context.update(self.failure(result))
        elif state in ("queued", "running"):
            context.update(self.pending(state, result, backend.alias))
        return context

    @staticmethod
    def gone(reason):
        return {"state": "unavailable", "reason": reason, "status": 404}

    @staticmethod
    def output(value) -> dict:
        """Bound what is rendered, whatever the backend handed back."""
        value = value if isinstance(value, dict) else {}
        limit = get_setting("COMMANDS_OUTPUT_LIMIT")
        stdout, stderr = str(value.get("stdout") or ""), str(value.get("stderr") or "")
        return {
            "stdout": stdout[:limit],
            "stderr": stderr[:limit],
            "truncated": bool(value.get("truncated")) or max(len(stdout), len(stderr)) > limit,
            "limit": limit,
        }

    def failure(self, result) -> dict:
        """The runner's own failure summary and output; never the whole traceback."""
        error = result.errors[-1] if result.errors else None
        path = getattr(error, "exception_class_path", "") or ""
        traceback = getattr(error, "traceback", "") or ""
        marker = f"{path}: "
        if path.startswith(f"{__package__}.tasks.") and marker in traceback:
            try:
                details = json.loads(traceback.rsplit(marker, 1)[1].strip())
            except ValueError:
                details = None
            if isinstance(details, dict):
                return {"error": str(details.get("error") or ""), **self.output(details)}
        return {"error": _("The worker failed with %s.") % (path or _("an unknown error"))}

    @staticmethod
    def pending(state, result, alias) -> dict:
        since = result.started_at if state == "running" else result.enqueued_at
        stale_after = get_setting("COMMANDS_STALE_AFTER")
        age = (timezone.now() - since).total_seconds() if since else 0
        if age <= stale_after:
            return {"refresh": REFRESH_SECONDS}
        minutes = int(age // 60)
        if state == "running":
            warning = _(
                "Still running after %(minutes)d minutes; the worker may have stopped. "
                "It is not retried automatically."
            ) % {"minutes": minutes}
        else:
            warning = _(
                "Still queued after %(minutes)d minutes. Is a worker running for the Tasks "
                "backend %(alias)r?"
            ) % {"minutes": minutes, "alias": alias}
        return {"stale": warning}
