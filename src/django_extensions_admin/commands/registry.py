"""Explicit registrations: the only management commands the admin will ever launch.

The registry is module level, like ``admin.site``, so the web process and the worker read
the same one - provided both import the module that registers. With the default
``django.contrib.admin`` (``AdminConfig``), autodiscovery imports every ``admin.py`` in
each process that calls ``django.setup()``, the task worker included. With
``SimpleAdminConfig`` it does not; register from a module that both processes import,
such as an ``AppConfig.ready()``. A worker that lacks a registration refuses the run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from django import forms
from django.core.exceptions import ImproperlyConfigured
from django.core.management import BaseCommand, get_commands, load_command_class
from django.db.models import QuerySet
from django.utils.text import capfirst

__all__ = [
    "PayloadError",
    "Registration",
    "build_payload",
    "command_arguments",
    "get",
    "register",
    "registrations",
]

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
        """The admin's own boundary (an active staff member) plus this command's permission.

        The pages are behind ``admin_view`` as well; the worker has only this check.
        """
        return bool(user.is_active and user.is_staff and user.has_perm(self.permission))

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

    Keyed exactly as the widgets read them - a split date/time field travels as its two
    sub-inputs - so the worker binds a fresh form to this payload and validates it
    again, and a model choice travels as its key and is looked up anew. Values that
    would not come back the same way raise PayloadError here, before anything is queued.
    """
    payload = {}
    for bound in form:
        payload.update(_widget_data(bound.field.widget, bound.html_name, bound.data))
    try:
        payload = json.loads(json.dumps(payload))
    except (TypeError, ValueError) as exc:
        raise PayloadError(str(exc)) from exc
    again = type(form)(data=payload)
    if not again.is_valid() or _meaning(again) != _meaning(form):
        raise PayloadError("the values change when the form is validated again")
    return payload


def _widget_data(widget, name, value) -> dict:
    """Undo ``MultiWidget.value_from_datadict``: one key per sub-widget, as submitted."""
    if isinstance(widget, forms.MultiWidget):
        values = value if isinstance(value, list | tuple) else [None] * len(widget.widgets)
        data = {}
        for sub_widget, suffix, sub_value in zip(
            widget.widgets, widget.widgets_names, values, strict=False
        ):
            data.update(_widget_data(sub_widget, f"{name}{suffix}", sub_value))
        return data
    return {name: value}


def _meaning(form) -> dict:
    """``cleaned_data`` as each field would display it again: model choices as their keys.

    Two validations of one input give equal meanings even where the objects differ; a
    ModelMultipleChoiceField returns a new QuerySet each time, and QuerySets compare by
    identity.
    """
    meaning = {}
    for name, value in form.cleaned_data.items():
        field = form.fields.get(name)
        meaning[name] = field.prepare_value(value) if field is not None else value
        if isinstance(meaning[name], QuerySet):
            meaning[name] = [item.pk for item in meaning[name]]
    return meaning


def command_arguments(form) -> dict:
    """The ``call_command`` keyword arguments for a valid *form*.

    A field that is not required and was left blank - its cleaned value is one of the
    field's own ``empty_values``, or an empty queryset - is left out, so the command's
    own argparse default applies. Everything else is passed, including a ``False`` from
    an unticked BooleanField.
    """
    arguments = {}
    for name, value in form.cleaned_data.items():
        field = form.fields.get(name)
        if field is not None and not field.required and _blank(field, value):
            continue
        arguments[name] = value
    return arguments


def _blank(field, value) -> bool:
    if isinstance(value, QuerySet):
        return not value.exists()
    return any(value is empty or value == empty for empty in field.empty_values)
