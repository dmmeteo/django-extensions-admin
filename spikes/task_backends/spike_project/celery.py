"""Celery app for the celery lane. Imported only when SPIKE_BACKEND=celery."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "spike_project.settings")

app = Celery("spike_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
