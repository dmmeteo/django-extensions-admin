"""Browser tests run against the demo project, on a disposable database."""

import os
import sys

# Playwright's sync API runs its own event loop, which makes Django think every ORM call
# happens in an async context. These tests are single-threaded and deliberately blocking.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo")
)

from demoproject.settings import *  # noqa: F403

DEBUG = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
ALLOWED_HOSTS = ["*"]
