"""Start and stop a real ``db_worker`` process for the length of a test."""

import os
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def worker_env(settings_module: str, extra: dict | None = None) -> dict:
    """The environment of a process that shares the running test database."""
    path = os.pathsep.join([str(ROOT / "src"), str(ROOT), os.environ.get("PYTHONPATH", "")])
    return {
        **os.environ,
        "PYTHONPATH": path,
        "DJANGO_SETTINGS_MODULE": settings_module,
        "WORKER_USE_TEST_DB": "1",
        **(extra or {}),
    }


def manage(settings_module: str, *argv: str, extra_env: dict | None = None):
    """Run one management command in a separate process, against the test database."""
    return subprocess.run(  # noqa: S603 - our own interpreter and arguments
        [sys.executable, "-m", "django", *argv],
        cwd=ROOT,
        env=worker_env(settings_module, extra_env),
        capture_output=True,
        text=True,
        check=True,
    )


@contextmanager
def db_worker(settings_module: str, log_path: Path, *, backend="commands", extra_env=None):
    """A worker serving *backend*; SIGTERM on exit, then a bounded wait, then SIGKILL."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-m",
        "django",
        "db_worker",
        "--no-reload",
        "--no-startup-delay",
        "--interval",
        "0.2",
        "--backend",
        backend,
        "--queue-name",
        "default",
    ]
    with log_path.open("a") as log:
        process = subprocess.Popen(  # noqa: S603 - our own interpreter and arguments
            argv,
            cwd=ROOT,
            env=worker_env(settings_module, extra_env),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            yield process
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
