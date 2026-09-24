"""A Tasks backend that claims results but whose queue is down: nothing is ever stored."""

from importlib import import_module

from django.conf import settings

BaseTaskBackend = import_module(f"{settings.TASKS_PACKAGE}.backends.base").BaseTaskBackend


class UnreachableBackend(BaseTaskBackend):
    supports_get_result = True

    def enqueue(self, task, args, kwargs):
        raise ConnectionError("queue unreachable")
