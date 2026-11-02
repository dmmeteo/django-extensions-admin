"""The one door to the Django Tasks API, and what the runner requires of a backend.

Django 6.0 ships ``django.tasks``; Django 5.2 gets the same objects from the
``django_tasks`` backport, with two exceptions renamed. Nothing else in this package
imports either, and nothing outside ``commands`` imports this module, so buttons, the
JSON widget and the filters never load a Tasks package.
"""

from __future__ import annotations

from functools import cache
from importlib import import_module
from importlib.util import find_spec
from types import SimpleNamespace

from django.core.exceptions import ImproperlyConfigured

from ..conf import get_setting

__all__ = ["CommandsUnavailable", "get_backend", "tasks_api"]

INSTALL_HINT = (
    'Install "django-tasks-db" on Django 6.0, or "django-tasks-db[compat]" on Django 5.2 '
    '(and add "django_tasks" to INSTALLED_APPS there).'
)


class CommandsUnavailable(Exception):
    """The runner cannot launch anything; the message says why, for the admin page."""


@cache
def tasks_api() -> SimpleNamespace:
    if find_spec("django.tasks") is not None:
        module = "django.tasks"
        exceptions = import_module("django.tasks.exceptions")
        invalid_task = exceptions.InvalidTask
        invalid_backend = exceptions.InvalidTaskBackend
    elif find_spec("django_tasks") is not None:
        module = "django_tasks"
        exceptions = import_module("django_tasks.exceptions")
        invalid_task = exceptions.InvalidTaskError
        invalid_backend = exceptions.InvalidTaskBackendError
    else:
        raise CommandsUnavailable(f"The Django Tasks API is not installed. {INSTALL_HINT}")
    api = import_module(module)
    return SimpleNamespace(
        module=module,
        task=api.task,
        task_backends=api.task_backends,
        TaskResultStatus=import_module(f"{module}.base").TaskResultStatus,
        InvalidTask=invalid_task,
        InvalidTaskBackend=invalid_backend,
        TaskResultDoesNotExist=exceptions.TaskResultDoesNotExist,
        ImmediateBackend=import_module(f"{module}.backends.immediate").ImmediateBackend,
        DummyBackend=import_module(f"{module}.backends.dummy").DummyBackend,
    )


def get_backend():
    """The configured Tasks backend, or CommandsUnavailable saying what is wrong.

    Never falls back: an unset alias does not mean Django's "default", and a backend that
    would run the command inline or never is refused, not used.
    """
    api = tasks_api()
    alias = get_setting("COMMANDS_TASK_BACKEND")
    if not alias:
        raise CommandsUnavailable(
            "ADMIN_EXTENSIONS['COMMANDS_TASK_BACKEND'] is not set. Name the settings.TASKS "
            "alias whose worker runs admin commands."
        )
    try:
        backend = api.task_backends[alias]
    except ImproperlyConfigured as exc:  # InvalidTaskBackend subclasses it on both APIs
        raise CommandsUnavailable(
            f"The Tasks backend alias {alias!r} is not usable: {exc}. Add it to settings.TASKS."
        ) from exc
    if isinstance(backend, api.ImmediateBackend | api.DummyBackend):
        raise CommandsUnavailable(
            f"The Tasks backend {alias!r} is a {type(backend).__name__}, which runs tasks "
            f"inside the request or never. Configure a backend with a worker, such as "
            f"django_tasks_db.DatabaseBackend."
        )
    if not backend.supports_get_result:
        raise CommandsUnavailable(
            f"The Tasks backend {alias!r} ({type(backend).__name__}) cannot read results "
            f"back, so the admin could never show a command's status."
        )
    return backend
