"""Harmless tasks whose return values expose where and how they ran."""

import datetime
import io
import os
import pathlib
import socket
import time

from django.conf import settings
from django.core.management import call_command

from .compat import task

# The only command the runner-shaped task accepts. Anything else fails in the worker.
ALLOWED_COMMANDS = {"hello": "spike_hello"}
OUTPUT_LIMIT = 4096


def _where():
    return {"pid": os.getpid(), "ppid": os.getppid(), "host": socket.gethostname()}


def _mark(tag, stage):
    if tag:
        path = pathlib.Path(settings.MARKERS)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{tag}.{stage}").write_text(str(time.time()))


@task
def echo(payload=None, tag=None, sleep=0, **extra):
    _mark(tag, "start")
    time.sleep(sleep)
    _mark(tag, "end")
    return {"where": _where(), "payload": payload, "extra": extra}


@task(queue_name="ops")
def echo_ops(payload=None, tag=None):
    _mark(tag, "start")
    return {"where": _where(), "payload": payload}


@task
def fail(message="deliberate failure", tag=None):
    _mark(tag, "start")
    raise ValueError(message)


@task
def bad_return(kind="set", tag=None):
    _mark(tag, "start")
    values = {
        "set": {1, 2},
        "datetime": datetime.datetime.now(datetime.UTC),
        "bytes": b"raw",
        "object": object(),
    }
    return values[kind]


@task
def slow(seconds=8, tag=None):
    _mark(tag, "start")
    time.sleep(seconds)
    _mark(tag, "end")
    return {"where": _where(), "slept": seconds}


@task
def read_row(tag):
    """Report whether the enqueuer's Marker row is visible from the worker."""
    from .models import Marker

    _mark(tag, "start")
    return {"where": _where(), "tag": tag, "found": Marker.objects.filter(tag=tag).exists()}


@task(takes_context=True)
def with_context(context, tag=None):
    _mark(tag, "start")
    return {
        "where": _where(),
        "attempt": context.attempt,
        "result_id": context.task_result.id,
        "backend": context.task_result.backend,
    }


@task
def run_command(key, options=None):
    """Runner-shaped shape check: a registered key and JSON options, rechecked here."""
    if key not in ALLOWED_COMMANDS:
        raise PermissionError(f"command {key!r} is not allowed")
    out = io.StringIO()
    call_command(ALLOWED_COMMANDS[key], stdout=out, **(options or {}))
    text = out.getvalue()
    return {"where": _where(), "output": text[:OUTPUT_LIMIT], "truncated": len(text) > OUTPUT_LIMIT}
