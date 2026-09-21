"""Settings access for django-extensions-admin.

All settings live under a single ``ADMIN_EXTENSIONS`` dict so a project adds at most one
entry to its settings module.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings

DEFAULTS: dict[str, Any] = {
    # Install PrettyJSONWidget as the admin-wide default for models.JSONField.
    # Off by default: a library should not change how an existing admin looks
    # until the project asks for it.
    "JSON_WIDGET_DEFAULT": False,
    # Values longer than this are rendered exactly as stored, with highlighting off.
    "JSON_MAX_PRETTY_CHARS": 100_000,
    "JSON_INDENT": 2,
    # Rewrite the field when it loses focus. Off by default: reformatting moves the
    # caret and interrupts native undo. The explicit "Format" control always works.
    "JSON_REFORMAT_ON_BLUR": False,
}


def get_setting(name: str) -> Any:
    """Return one ADMIN_EXTENSIONS setting, falling back to the documented default."""
    configured = getattr(settings, "ADMIN_EXTENSIONS", None) or {}
    if name not in DEFAULTS:
        raise KeyError(f"Unknown ADMIN_EXTENSIONS setting {name!r}")
    return configured.get(name, DEFAULTS[name])
