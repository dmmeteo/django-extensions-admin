import dataclasses
import itertools
import time
from pathlib import Path

from django_extensions_admin.repl.conf import Facts, get_config
from django_extensions_admin.repl.sessions import manager

_owner_ids = itertools.count(10_000)


def wait_for(predicate, timeout=15.0, message="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(f"Timed out after {timeout}s waiting for {message}")


def screen(session):
    return session.read(0)[1].decode("utf-8", "replace")


def wait_output(session, needle, timeout=20.0):
    def found():
        text = screen(session)
        return text if needle in text else None

    return wait_for(found, timeout, f"{needle!r} in REPL output:\n{screen(session)[-800:]}")


def alive(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (FileNotFoundError, ProcessLookupError):
        return False
    return fields[0] != "Z"


class StartedSessions:
    """Starts sessions for synthetic owners and ends every one of them at cleanup."""

    def __init__(self, test_case):
        self.owners = []
        test_case.addCleanup(self.end_all)

    def start(self, backend="python", **overrides):
        config = dataclasses.replace(get_config(), **overrides)
        owner_id = next(_owner_ids)
        session, created = manager.start(owner_id, config.offered(Facts.observe())[backend], config)
        assert created
        self.owners.append(owner_id)
        return session

    def end_all(self):
        for owner_id in self.owners:
            manager.end(owner_id)
