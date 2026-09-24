"""System checks for the command runner. Registered only when a project imports it."""

from __future__ import annotations

from django.apps import apps
from django.core import checks

from . import registry
from .backend import CommandsUnavailable, get_backend, tasks_api


@checks.register()
def check_command_runner(app_configs=None, **kwargs):
    messages = []
    try:
        api = tasks_api()
        backend = get_backend()
    except CommandsUnavailable as exc:
        messages.append(checks.Error(str(exc), id="django_extensions_admin.E101"))
    else:
        if api.module == "django_tasks" and not apps.is_installed("django_tasks"):
            messages.append(
                checks.Error(
                    'On Django 5.2 the Tasks backport must be installed: add "django_tasks" '
                    "to INSTALLED_APPS.",
                    id="django_extensions_admin.E102",
                )
            )
        backend_path = f"{type(backend).__module__}.{type(backend).__qualname__}"
        if not backend_path.startswith("django_tasks_db."):
            messages.append(
                checks.Warning(
                    f"The command runner is tested with django_tasks_db.DatabaseBackend only; "
                    f"{backend_path} is unverified.",
                    hint="Unknown results, transactions and lost workers behave differently "
                    "per backend. See the django-extensions-admin README.",
                    id="django_extensions_admin.W101",
                )
            )
    for registration in registry.registrations():
        messages.extend(_check_registration(registration))
    return messages


def _check_registration(registration):
    try:
        command = registration.load_command()
    except KeyError:
        return [
            checks.Error(
                f"The registered admin command {registration.name!r} is not a management "
                f"command of any installed app.",
                id="django_extensions_admin.E103",
            )
        ]
    parser = command.create_parser("", registration.name)
    options = {
        action.dest for action in parser._actions if action.option_strings and action.dest != "help"
    }
    return [
        checks.Error(
            f"{registration.form.__name__}.{field_name} is not an option of the "
            f"{registration.name!r} command. Form field names must be the command's option "
            f"names (dest); positional arguments are not supported.",
            id="django_extensions_admin.E104",
        )
        for field_name in registration.form.base_fields
        if field_name not in options
    ]
