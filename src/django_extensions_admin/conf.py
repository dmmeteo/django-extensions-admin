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
    "JSON_MAX_PRETTY_CHARS": 200_000,
    "JSON_INDENT": 2,
    # Rewrite the field when it loses focus. Off by default: reformatting moves the
    # caret and interrupts native undo. The explicit "Format" control always works.
    "JSON_REFORMAT_ON_BLUR": False,
    # The command runner (django_extensions_admin.commands) reads these only once a
    # project adopts it. The Tasks backend alias - a key of settings.TASKS - that runs
    # launched commands. No default on purpose: Django's own default alias is the
    # ImmediateBackend, which would run "background" work inside the admin request.
    "COMMANDS_TASK_BACKEND": None,
    # Characters kept from each of a command's stdout and stderr.
    "COMMANDS_OUTPUT_LIMIT": 20_000,
    # Seconds after which a queued or running command is reported as possibly stuck.
    "COMMANDS_STALE_AFTER": 30 * 60,
    # Logo and colours for the admin header (django_extensions_admin.branding). Read only
    # by the branding template, which a project adopts in its own admin/base_site.html;
    # the setting alone changes nothing.
    "BRANDING": None,
    # The environment indicator (django_extensions_admin.environment): a name such as
    # "Staging", or a dict with NAME, COLOR, POSITION and HEIGHT. Empty means no indicator.
    "ENVIRONMENT": "",
    # Which edge the shared tools panel (django_extensions_admin.panel) docks to.
    "PANEL_SIDE": "right",
    # The REPL tool (django_extensions_admin.repl). Off until a project turns it on: it runs
    # arbitrary Python with the application's privileges.
    "REPL_ENABLED": False,
    # "auto" or one of python, ipython, shell_plus.
    "REPL_BACKEND": "auto",
    # None offers every installed backend; a list limits what the browser may pick.
    "REPL_ALLOWED_BACKENDS": None,
    # Seconds without input after which a session's process is ended.
    "REPL_IDLE_TIMEOUT": 4 * 60 * 60,
    # Bytes of output kept per session for reattaching after navigation or reload.
    "REPL_REPLAY_BYTES": 512 * 1024,
    # The WebSocket path the project's ASGI router sends to the REPL consumer.
    "REPL_STREAM_PATH": "/admin/repl/stream/",
    # The file one server process locks to host sessions. None: a file in the temp dir.
    "REPL_LOCK_PATH": None,
}


def get_setting(name: str) -> Any:
    """Return one ADMIN_EXTENSIONS setting, falling back to the documented default."""
    configured = getattr(settings, "ADMIN_EXTENSIONS", None) or {}
    if name not in DEFAULTS:
        raise KeyError(f"Unknown ADMIN_EXTENSIONS setting {name!r}")
    return configured.get(name, DEFAULTS[name])
