"""The one Django Task: run a registered command in the worker, after checking it again.

Imported only once the configured backend has been validated (and by the worker, from
the task path it stored), because defining a Task validates it against its backend.
"""

from __future__ import annotations

import io
import json

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import transaction

from ..conf import get_setting
from . import registry
from .backend import tasks_api

__all__ = [
    "CommandFailed",
    "CommandNotAllowed",
    "InvalidCommandOptions",
    "enqueue_on_commit",
    "run_command",
]

ERROR_LIMIT = 2_000


class CommandRunError(Exception):
    """Base of the failures this task records. The message is JSON for the result page."""

    def __init__(self, error: str, stdout: str = "", stderr: str = "", truncated=False):
        self.error = error[:ERROR_LIMIT]
        super().__init__(
            json.dumps(
                {"error": self.error, "stdout": stdout, "stderr": stderr, "truncated": truncated}
            )
        )


class CommandNotAllowed(CommandRunError):
    """The worker's own registry or the launching user's permission says no."""


class InvalidCommandOptions(CommandRunError):
    """The payload does not validate against the registered form in the worker."""


class CommandFailed(CommandRunError):
    """The command itself raised."""


class BoundedOutput(io.StringIO):
    """Keeps the first *limit* characters written to it and remembers if it dropped any."""

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit
        self.kept = 0
        self.truncated = False

    def write(self, text):
        room = self.limit - self.kept
        if len(text) > room:
            self.truncated = True
        kept = text[: max(room, 0)]
        if kept:
            super().write(kept)
            self.kept += len(kept)
        return len(text)


def run_command(key, options, actor_id):
    """Revalidate everything the admin checked, then ``call_command``.

    Nothing here trusts the stored payload: the key must be registered in *this*
    process, the user must still hold the permission, and the options must validate
    against the registered form. The return value is JSON by construction.
    """
    registration = registry.get(key)
    if registration is None:
        raise CommandNotAllowed(f"{key!r} is not a registered admin command in this worker.")
    user = get_user_model()._default_manager.filter(pk=actor_id).first()
    if user is None or not registration.has_permission(user):
        raise CommandNotAllowed("The user who launched this command may no longer run it.")
    form = registration.form(data=options if isinstance(options, dict) else {})
    if not form.is_valid():
        raise InvalidCommandOptions(f"Invalid options: {form.errors.get_json_data()}")

    limit = get_setting("COMMANDS_OUTPUT_LIMIT")
    stdout, stderr = BoundedOutput(limit), BoundedOutput(limit)
    arguments = dict(form.cleaned_data)
    command = registration.load_command()
    parser = command.create_parser("", key)
    if any(action.dest == "interactive" for action in parser._actions):
        arguments["interactive"] = False  # nobody is there to answer a prompt
    try:
        call_command(command, stdout=stdout, stderr=stderr, **arguments)
    except Exception as exc:
        raise CommandFailed(
            f"{type(exc).__name__}: {exc}",
            stdout.getvalue(),
            stderr.getvalue(),
            stdout.truncated or stderr.truncated,
        ) from exc
    return {
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "truncated": stdout.truncated or stderr.truncated,
    }


run_command = tasks_api().task(backend=get_setting("COMMANDS_TASK_BACKEND"))(run_command)


def enqueue_on_commit(key: str, options: dict, actor_id, backend_alias: str):
    """Queue a run once the current transaction commits, and return its result if that
    is now.

    Returns None when a transaction is still open: the run is then published at commit,
    or never if it rolls back. The admin view refuses to launch in that state, because it
    could not hand back a reference to a run that does not exist yet.
    """
    queued = []

    def enqueue():
        task = run_command.using(backend=backend_alias)
        queued.append(task.enqueue(key=key, options=options, actor_id=actor_id))

    transaction.on_commit(enqueue)
    return queued[0] if queued else None
