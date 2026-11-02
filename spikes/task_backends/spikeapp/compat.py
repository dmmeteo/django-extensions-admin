"""The whole 5.2 compatibility surface the harness needed: one import switch.

The backport exposes the same objects under different module paths and, for two of
them, different exception names. Anything later product code imports from the Tasks
API has to go through a switch like this while Django 5.2 is supported.
"""

from importlib.util import find_spec

if find_spec("django.tasks"):
    from django.tasks import TaskResultStatus, task, task_backends
    from django.tasks.exceptions import InvalidTask, InvalidTaskBackend, TaskResultDoesNotExist

    TASKS_MODULE = "django.tasks"
else:
    from django_tasks import TaskResultStatus, task, task_backends
    from django_tasks.exceptions import InvalidTaskBackendError as InvalidTaskBackend
    from django_tasks.exceptions import InvalidTaskError as InvalidTask
    from django_tasks.exceptions import TaskResultDoesNotExist

    TASKS_MODULE = "django_tasks"

__all__ = [
    "TASKS_MODULE",
    "InvalidTask",
    "InvalidTaskBackend",
    "TaskResultDoesNotExist",
    "TaskResultStatus",
    "task",
    "task_backends",
]
