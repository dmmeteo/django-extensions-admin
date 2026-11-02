"""Launch explicitly registered management commands from the admin, in a task worker.

    from django_extensions_admin import commands

    commands.register("clearsessions", permission="sessions.delete_session")   # admin.py
    path("admin/commands/", commands.urls(admin.site)),                         # urls.py

Opt-in twice over: importing this module routes nothing, and ``urls()`` serves only what
``register()`` allowed. The Tasks API is imported when a page or the worker needs it,
never by the rest of django-extensions-admin.
"""

from . import checks as _checks  # noqa: F401 - registers the system checks
from .registry import register
from .views import urls

__all__ = ["register", "urls"]
