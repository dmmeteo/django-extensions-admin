"""Explicit registrations: the only management commands the admin will ever launch.

The registry is module level, like ``admin.site``, so the web process and the worker read
the same one. Register from an ``admin.py`` module: Django's admin autodiscovery imports
those in every process that calls ``django.setup()``, the task worker included.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from django import forms
from django.core.exceptions import ImproperlyConfigured
from django.core.management import BaseCommand, get_commands, load_command_class
from django.utils.text import capfirst

__all__ = ["PayloadError", "Registration", "build_payload", "get", "register", "registrations"]

#: Options the runner sets itself; a form may not supply them.
RESERVED_FIELDS = frozenset({"stdout", "stderr", "interactive"})

_registry: dict[str, Registration] = {}


class NoOptionsForm(forms.Form):
    """A command without options still runs from an explicit POST of this empty form."""


class PayloadError(ValueError):
    """The form's values do not survive the trip to a worker unchanged."""


@dataclass(frozen=True)
class Registration:
    name: str
    permission: str
    form: type[forms.BaseForm]
    description: str

    def has_permission(self, user) -> bool:
        return bool(user.is_active and user.has_perm(self.permission))

    def load_command(self) -> BaseCommand:
        """The command instance, as ``call_command`` would load it."""
        app = get_commands()[self.name]
        return app if isinstance(app, BaseCommand) else load_command_class(app, self.name)


def register(
    name: str,
    *,
    permission: str,
    form: type[forms.BaseForm] | None = None,
    description: str | None = None,
) -> Registration:
    """Allow the admin to launch the management command *name*.

    permission
        ``"app_label.codename"``, checked with ``user.has_perm`` when the form is shown,
        when it is posted, when a result is read, and again in the worker.
    form
        A plain ``forms.Form`` whose field names are the command's option names (their
        ``dest``). Its ``cleaned_data`` becomes the ``call_command`` keyword arguments.
        Omit it for a command without options.
    description
        The label in the admin. Defaults to the command name.
    """
    if not isinstance(name, str) or not name:
        raise ImproperlyConfigured("A command registration needs the command's name.")
    if name in _registry:
        raise ImproperlyConfigured(f"The command {name!r} is already registered.")
    app_label, _, codename = (permission or "").partition(".")
    if not (isinstance(permission, str) and app_label and codename):
        raise ImproperlyConfigured(
            f"The command {name!r} needs permission='app_label.codename'; got {permission!r}."
        )
    form = form or NoOptionsForm
    if not (isinstance(form, type) and issubclass(form, forms.BaseForm)):
        raise ImproperlyConfigured(f"The form for {name!r} must be a Django Form class.")
    for field_name, field in form.base_fields.items():
        if isinstance(field, forms.FileField):
            raise ImproperlyConfigured(
                f"{form.__name__}.{field_name} is a file field. Uploaded files cannot be "
                f"sent to a worker; accept a path or an identifier instead."
            )
        if field_name in RESERVED_FIELDS:
            raise ImproperlyConfigured(
                f"{form.__name__}.{field_name}: {field_name!r} is set by the runner itself."
            )
    registration = Registration(
        name=name,
        permission=permission,
        form=form,
        description=str(description) if description else capfirst(name.replace("_", " ")),
    )
    _registry[name] = registration
    return registration


def get(name) -> Registration | None:
    return _registry.get(name) if isinstance(name, str) else None


def registrations() -> list[Registration]:
    return list(_registry.values())


def build_payload(form: forms.BaseForm) -> dict:
    """The JSON a worker receives for a valid *form*: its submitted values, not objects.

    The worker binds a fresh form to this payload and validates it again, so a model
    choice travels as its key and is looked up anew. Values that would not come back the
    same way raise PayloadError here, before anything is queued.
    """
    payload = {bound.html_name: bound.data for bound in form}
    try:
        payload = json.loads(json.dumps(payload))
    except (TypeError, ValueError) as exc:
        raise PayloadError(str(exc)) from exc
    again = type(form)(data=payload)
    if not again.is_valid() or again.cleaned_data != form.cleaned_data:
        raise PayloadError("the values change when the form is validated again")
    return payload
