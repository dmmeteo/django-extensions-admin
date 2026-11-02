import importlib.util
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ..conf import get_setting

AUTO = "auto"


@dataclass(frozen=True)
class Facts:
    ipython: bool
    django_extensions: bool

    @classmethod
    def observe(cls) -> "Facts":
        return cls(
            ipython=importlib.util.find_spec("IPython") is not None,
            django_extensions=apps.is_installed("django_extensions"),
        )


@dataclass(frozen=True)
class Backend:
    key: str
    label: str
    argv: tuple[str, ...]


def available_backends(facts: Facts) -> dict[str, Backend]:
    backends = [Backend("python", "Django shell (Python)", ("shell", "--interface", "python"))]
    if facts.ipython:
        backends.append(
            Backend("ipython", "Django shell (IPython)", ("shell", "--interface", "ipython"))
        )
    if facts.django_extensions:
        interface = "--ipython" if facts.ipython else "--plain"
        label = "shell_plus (IPython)" if facts.ipython else "shell_plus (Python)"
        backends.append(Backend("shell_plus", label, ("shell_plus", interface)))
    return {backend.key: backend for backend in backends}


KNOWN_BACKENDS = ("python", "ipython", "shell_plus")


@dataclass(frozen=True)
class Config:
    enabled: bool
    backend: str
    allowed: tuple[str, ...] | None
    idle_timeout: int
    replay_bytes: int
    stream_path: str
    lock_path: Path

    def offered(self, facts: Facts) -> dict[str, Backend]:
        available = available_backends(facts)
        keys = self.allowed if self.allowed is not None else tuple(available)
        return {key: available[key] for key in keys if key in available}

    def default_backend(self, facts: Facts) -> Backend | None:
        offered = self.offered(facts)
        if self.backend != AUTO:
            return offered.get(self.backend)
        for key in ("ipython", "python", "shell_plus"):
            if key in offered:
                return offered[key]
        return None

    def problems(self, facts: Facts) -> list[str]:
        available = available_backends(facts)
        found = []
        if self.backend != AUTO and self.backend not in available:
            found.append(
                f"ADMIN_EXTENSIONS['REPL_BACKEND'] = {self.backend!r} is not available here."
            )
        if self.allowed is not None:
            if self.backend != AUTO and self.backend not in self.allowed:
                found.append(
                    f"ADMIN_EXTENSIONS['REPL_BACKEND'] = {self.backend!r} is not listed in"
                    " REPL_ALLOWED_BACKENDS."
                )
            missing = [key for key in self.allowed if key not in available]
            if missing:
                found.append(
                    "ADMIN_EXTENSIONS['REPL_ALLOWED_BACKENDS'] names unavailable backends:"
                    f" {', '.join(missing)}."
                )
        if not self.offered(facts):
            found.append("No REPL backend is available with the current REPL settings.")
        return found


def _positive_int(raw: object, name: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ImproperlyConfigured(
            f"ADMIN_EXTENSIONS[{name!r}] must be a positive integer, got {raw!r}."
        )
    return raw


def get_config() -> Config:
    enabled = get_setting("REPL_ENABLED")
    if not isinstance(enabled, bool):
        raise ImproperlyConfigured(
            f"ADMIN_EXTENSIONS['REPL_ENABLED'] must be True or False, got {enabled!r}."
        )

    backend = get_setting("REPL_BACKEND")
    if backend != AUTO and backend not in KNOWN_BACKENDS:
        raise ImproperlyConfigured(
            "ADMIN_EXTENSIONS['REPL_BACKEND'] must be 'auto' or one of"
            f" {', '.join(KNOWN_BACKENDS)}, got {backend!r}."
        )

    allowed = get_setting("REPL_ALLOWED_BACKENDS")
    if allowed is not None:
        if isinstance(allowed, str) or not all(isinstance(key, str) for key in allowed):
            raise ImproperlyConfigured(
                "ADMIN_EXTENSIONS['REPL_ALLOWED_BACKENDS'] must be a list of backend names or None."
            )
        allowed = tuple(allowed)
        unknown_keys = [key for key in allowed if key not in KNOWN_BACKENDS]
        if unknown_keys:
            raise ImproperlyConfigured(
                "ADMIN_EXTENSIONS['REPL_ALLOWED_BACKENDS'] has unknown names:"
                f" {', '.join(unknown_keys)}."
            )

    stream_path = get_setting("REPL_STREAM_PATH")
    if not (
        isinstance(stream_path, str) and stream_path.startswith("/") and stream_path.endswith("/")
    ):
        raise ImproperlyConfigured(
            "ADMIN_EXTENSIONS['REPL_STREAM_PATH'] must start and end with '/'."
        )

    # Per user and per settings module, so two projects on one host do not block each other.
    module = settings.SETTINGS_MODULE or os.environ.get("DJANGO_SETTINGS_MODULE") or "settings"
    user = os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    default_lock = f"django-extensions-admin-repl-{user}-{module}.lock"
    lock_path = get_setting("REPL_LOCK_PATH") or Path(tempfile.gettempdir()) / default_lock

    return Config(
        enabled=enabled,
        backend=backend,
        allowed=allowed,
        idle_timeout=_positive_int(get_setting("REPL_IDLE_TIMEOUT"), "REPL_IDLE_TIMEOUT"),
        replay_bytes=_positive_int(get_setting("REPL_REPLAY_BYTES"), "REPL_REPLAY_BYTES"),
        stream_path=stream_path,
        lock_path=Path(lock_path),
    )
