import sys
from collections.abc import Sequence
from typing import Any

from django.apps import AppConfig
from django.core.checks import CheckMessage, Error
from django.core.exceptions import ImproperlyConfigured

from .conf import Facts, get_config


def check_repl(app_configs: Sequence[AppConfig] | None, **kwargs: Any) -> list[CheckMessage]:
    try:
        config = get_config()
    except ImproperlyConfigured as error:
        return [Error(str(error), id="django_extensions_admin.E501")]
    if not config.enabled:
        return []
    from django.conf import settings

    errors = [
        Error(problem, id="django_extensions_admin.E502")
        for problem in config.problems(Facts.observe())
    ]
    if "*" in settings.ALLOWED_HOSTS:
        errors.append(
            Error(
                "REPL_ENABLED with '*' in ALLOWED_HOSTS lets a page on any origin open the REPL"
                " stream.",
                hint="List the admin's host names in ALLOWED_HOSTS.",
                id="django_extensions_admin.E503",
            )
        )
    if not sys.platform.startswith("linux"):
        errors.append(
            Error(
                f"The REPL needs Linux pseudo-terminals and /proc; this is {sys.platform}.",
                id="django_extensions_admin.E504",
            )
        )
    return errors
