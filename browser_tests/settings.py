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
# Named hosts: the REPL's WebSocket origin check is only as strict as this list.
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Every journey runs on the stock admin: the demo's branding adoption is taken out here,
# and test_branding puts it back with override_settings.
DEMO_TEMPLATES = TEMPLATES  # noqa: F405
DEMO_BRANDING = ADMIN_EXTENSIONS["BRANDING"]  # noqa: F405
TEMPLATES = [{**DEMO_TEMPLATES[0], "DIRS": []}]
ADMIN_EXTENSIONS = {k: v for k, v in ADMIN_EXTENSIONS.items() if k != "BRANDING"}  # noqa: F405
# The same goes for the indicator and the REPL: off in the live-server journeys. The ASGI
# server that test_panel starts reads its own values from the environment.
ADMIN_EXTENSIONS["ENVIRONMENT"] = os.environ.get("BROWSER_ENVIRONMENT", "")
if os.environ.get("BROWSER_ENVIRONMENT_POSITION"):
    ADMIN_EXTENSIONS["ENVIRONMENT"] = {
        "NAME": ADMIN_EXTENSIONS["ENVIRONMENT"],
        "POSITION": os.environ["BROWSER_ENVIRONMENT_POSITION"],
    }
ADMIN_EXTENSIONS["REPL_ENABLED"] = os.environ.get("BROWSER_REPL") == "1"
ADMIN_EXTENSIONS["PANEL_SIDE"] = os.environ.get("BROWSER_PANEL_SIDE", "right")
ADMIN_EXTENSIONS["REPL_LOCK_PATH"] = str(_DB_DIR / "repl.lock")
if os.environ.get("BROWSER_IDLE_TIMEOUT"):
    ADMIN_EXTENSIONS["REPL_IDLE_TIMEOUT"] = int(os.environ["BROWSER_IDLE_TIMEOUT"])
