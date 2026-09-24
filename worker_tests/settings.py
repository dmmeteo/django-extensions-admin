"""The unit-test settings, on a database a separately started worker can share, with a
UUID-keyed custom user model.

SQLite file by default (one worker; django-tasks-db takes exclusive transactions), or a
disposable PostgreSQL when WORKER_PG="host:port" is set. The test runner creates the
test database; a worker started with WORKER_USE_TEST_DB=1 connects to that same one.
"""

import os
from pathlib import Path

from tests.settings import *  # noqa: F403

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = Path(os.environ.get("WORKER_ARTIFACTS") or ROOT / "artifacts" / "worker")

# Every journey here runs as a user whose primary key is a UUID, not an integer.
INSTALLED_APPS = [*INSTALLED_APPS, "worker_tests.accounts"]  # noqa: F405
AUTH_USER_MODEL = "worker_accounts.User"

if pg := os.environ.get("WORKER_PG"):
    host, port = pg.split(":")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": host,
            "PORT": port,
            "NAME": "deadmin",
            "USER": "deadmin",
            "PASSWORD": "deadmin",
            "TEST": {"NAME": "deadmin_test"},
        }
    }
else:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(ARTIFACTS / "worker.sqlite3"),
            "TEST": {"NAME": str(ARTIFACTS / "worker-test.sqlite3")},
            "OPTIONS": {"timeout": 20},
        }
    }

if os.environ.get("WORKER_USE_TEST_DB"):
    DATABASES["default"]["NAME"] = DATABASES["default"]["TEST"]["NAME"]
