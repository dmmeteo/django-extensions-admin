"""Demo settings. Disposable SQLite, loopback only, generated data only."""

import os
from importlib.util import find_spec
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Local demo only: this project is never deployed, and the database is throwaway.
SECRET_KEY = "demo-only-not-a-secret"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

INSTALLED_APPS = [
    "django_extensions_admin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tasks_db",
    "demoapp",
]
# Django 5.2 only: the Tasks API comes from the django-tasks backport.
if find_spec("django.tasks") is None:
    INSTALLED_APPS.insert(-2, "django_tasks")

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "demoproject.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DEMO_DB", str(BASE_DIR / "demo.sqlite3")),
    }
}

STATIC_URL = "/static/"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Project-wide opt-in: every JSONField in this admin gets the widget, with no
# per-ModelAdmin configuration. An admin that sets its own widget still wins.
# The command runner's queue is a table in this same database; scripts/demo.sh starts
# `manage.py db_worker --backend commands` next to the server.
TASKS = {"commands": {"BACKEND": "django_tasks_db.DatabaseBackend"}}

ADMIN_EXTENSIONS = {"JSON_WIDGET_DEFAULT": True, "COMMANDS_TASK_BACKEND": "commands"}
