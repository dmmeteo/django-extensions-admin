"""Settings for the task-backend spike, driven entirely by environment variables.

SPIKE_BACKEND   "db" (django-tasks-db) or "celery" (django-tasks-celery)
SPIKE_PG        "host:port" of a disposable PostgreSQL; SQLite at SPIKE_SQLITE otherwise
SPIKE_REDIS     redis:// URL of a disposable broker/result store (celery only)
SPIKE_MARKERS   directory the tasks write start/finish markers into
"""

import os
from importlib.util import find_spec

import django

SECRET_KEY = "spike-not-secret"
DEBUG = False
USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

BACKEND = os.environ.get("SPIKE_BACKEND", "db")
NATIVE = find_spec("django.tasks") is not None
TASKS_PKG = "django.tasks" if NATIVE else "django_tasks"

INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.auth", "spikeapp"]
if not NATIVE:
    INSTALLED_APPS.append("django_tasks")
if BACKEND == "db":
    INSTALLED_APPS.append("django_tasks_db")

if pg := os.environ.get("SPIKE_PG"):
    host, port = pg.split(":")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": host,
            "PORT": port,
            "NAME": "spike",
            "USER": "spike",
            "PASSWORD": "spike",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SPIKE_SQLITE", "spike.sqlite3"),
            "OPTIONS": {"timeout": 20},
        }
    }

# Contrast aliases only. Neither one is background execution.
CONTRAST = {
    "immediate": {"BACKEND": f"{TASKS_PKG}.backends.immediate.ImmediateBackend"},
    "dummy": {"BACKEND": f"{TASKS_PKG}.backends.dummy.DummyBackend"},
}

if BACKEND == "db":
    TASKS = {
        "default": {"BACKEND": "django_tasks_db.DatabaseBackend", "QUEUES": ["default", "ops"]},
        "ops": {"BACKEND": "django_tasks_db.DatabaseBackend", "QUEUES": ["ops"]},
        **CONTRAST,
    }
else:
    CELERY_BROKER_URL = os.environ["SPIKE_REDIS"] + "/0"
    CELERY_RESULT_BACKEND = os.environ["SPIKE_REDIS"] + "/1"
    CELERY_RESULT_EXTENDED = True
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_WORKER_HIJACK_ROOT_LOGGER = False
    if os.environ.get("SPIKE_CELERY_ACKS_LATE"):
        # Explicit opt-in used by one shutdown scenario: redeliver work lost with a worker.
        CELERY_TASK_ACKS_LATE = True
        CELERY_TASK_REJECT_ON_WORKER_LOST = True
        CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 10}
    celery_options = {"CELERY_APP": "spike_project.celery.app"}
    TASKS = {
        "default": {
            "BACKEND": "django_tasks_celery.CeleryBackend",
            "QUEUES": ["default", "ops"],
            "OPTIONS": celery_options,
        },
        "ops": {
            "BACKEND": "django_tasks_celery.CeleryBackend",
            "QUEUES": ["ops"],
            "OPTIONS": celery_options,
        },
        **CONTRAST,
    }

MARKERS = os.environ.get("SPIKE_MARKERS", "markers")
DJANGO_VERSION = django.get_version()
