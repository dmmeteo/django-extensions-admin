"""Browser tests run against the demo project, on a disposable database."""

import os
import sys
from pathlib import Path

# Playwright's sync API runs its own event loop, which makes Django think every ORM call
# happens in an async context. These tests are single-threaded and deliberately blocking.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo")
)

from demoproject.settings import *  # noqa: F403

DEBUG = False
# A file, not :memory:, so the command-runner journey's separately started db_worker can
# share the live server's test database. Disposable: the test runner recreates it.
_DB_DIR = (
    Path(
        os.environ.get("ADMIN_EXTENSIONS_ARTIFACTS")
        or Path(__file__).resolve().parent.parent / "artifacts" / "browser"
    ).parent
    / "browser-db"
)
_DB_DIR.mkdir(parents=True, exist_ok=True)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(_DB_DIR / "browser.sqlite3"),
        "TEST": {"NAME": str(_DB_DIR / "browser-test.sqlite3")},
        "OPTIONS": {"timeout": 20},
    }
}
if os.environ.get("WORKER_USE_TEST_DB"):
    DATABASES["default"]["NAME"] = DATABASES["default"]["TEST"]["NAME"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ALLOWED_HOSTS = ["*"]
