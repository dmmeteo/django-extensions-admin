"""A real daphne process serving browser_tests.asgi on the live test database."""

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class AsgiServer:
    def __init__(self, log_path: Path, env: dict[str, str]):
        self.log_path = log_path
        self.env = env
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.process = None

    def start(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log = self.log_path.open("a")
        self.process = subprocess.Popen(  # noqa: S603 - our own interpreter and arguments
            [
                sys.executable,
                "-m",
                "daphne",
                "-b",
                "127.0.0.1",
                "-p",
                str(self.port),
                "browser_tests.asgi:application",
            ],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join([str(ROOT), os.environ.get("PYTHONPATH", "")]),
                "DJANGO_SETTINGS_MODULE": "browser_tests.settings",
                "WORKER_USE_TEST_DB": "1",
                **self.env,
            },
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"daphne exited with {self.process.returncode}; see {self.log_path}"
                )
            try:
                with urllib.request.urlopen(f"{self.url}/admin/login/", timeout=2):  # noqa: S310 - loopback
                    return self
            except OSError:
                time.sleep(0.2)
        raise RuntimeError(f"daphne did not answer within 60 s; see {self.log_path}")

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def restart(self):
        self.stop()
        return self.start()


@contextmanager
def asgi_server(log_path: Path, **env):
    server = AsgiServer(log_path, env).start()
    try:
        yield server
    finally:
        server.stop()
