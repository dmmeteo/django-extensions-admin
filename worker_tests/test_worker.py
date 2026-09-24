"""Journeys through the admin with a real, separately started ``db_worker`` process.

    PYTHONPATH=src:. DJANGO_SETTINGS_MODULE=worker_tests.settings \\
        python tests/runtests.py worker_tests

Three processes take part: this test process (the admin), the worker, and for pruning a
third ``manage.py`` process. Nothing is mocked on the worker side. The user model here
has a UUID primary key, so the actor id and the signed reference are proven for a
non-integer key end to end.
"""

import os
import re
import time
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connections
from django.test import TransactionTestCase
from django_tasks_db.models import DBTaskResult

from tests.testapp.models import Device

from .process import db_worker, manage
from .settings import ARTIFACTS

SETTINGS = "worker_tests.settings"
STATE = re.compile(r'data-state="(\w+)"')


class RealWorkerTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "run", "run@example.invalid", "pw", is_staff=True
        )
        self.user.user_permissions.add(Permission.objects.get(codename="run_device_commands"))
        self.client.force_login(self.user)

    def worker(self):
        return db_worker(SETTINGS, ARTIFACTS / f"{self._testMethodName}.log")

    def launch(self, name="admin_ext_echo", data=None):
        response = self.client.post(f"/admin/commands/{name}/", data or {})
        self.assertEqual(response.status_code, 302, response.content[:2000])
        return response["Location"]

    def state(self, location):
        response = self.client.get(location)
        return STATE.search(response.content.decode())[1], response

    def wait_until_finished(self, location, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state, response = self.state(location)
            if state in ("succeeded", "failed"):
                return state, response
            time.sleep(0.2)
        self.fail(f"the run at {location} did not finish within {timeout}s")

    def test_a_run_waits_for_a_worker_and_runs_in_that_process(self):
        location = self.launch(data={"message": "from the admin", "times": "2", "touch": "w"})
        time.sleep(1)
        self.assertEqual(self.state(location)[0], "queued")
        self.assertFalse(Device.objects.filter(name="w").exists())
        with self.worker() as worker:
            state, response = self.wait_until_finished(location)
        self.assertEqual(state, "succeeded")
        self.assertContains(response, "from the admin\nfrom the admin\n")
        self.assertContains(response, f"pid={worker.pid}")
        self.assertNotEqual(worker.pid, os.getpid())
        self.assertTrue(Device.objects.filter(name="w").exists())
        self.assertEqual(worker.returncode, 0)
        # The UUID actor went through the queue as a string and was found by the worker.
        self.assertIsInstance(self.user.pk, uuid.UUID)
        self.assertEqual(
            DBTaskResult.objects.get().args_kwargs["kwargs"]["actor_id"], str(self.user.pk)
        )

    def test_multi_value_and_blank_options_cross_the_process_boundary(self):
        alpha, beta = Device.objects.create(name="alpha"), Device.objects.create(name="beta")
        filled = self.launch(
            "admin_ext_options",
            {
                "kinds": ["sensor", "relay"],
                "devices": [str(alpha.pk), str(beta.pk)],
                "when_0": "2026-09-24",
                "when_1": "10:30:00",
            },
        )
        with self.worker():
            state, response = self.wait_until_finished(filled)
        self.assertEqual(state, "succeeded")
        stdout = response.context["stdout"]
        for line in (
            "limit=100",  # left blank: the command's own default
            "label='untitled'",
            "dry_run=False",
            "kinds=['sensor', 'relay']",
            "devices=['alpha', 'beta']",
            "when='2026-09-24T10:30:00",
        ):
            self.assertIn(line, stdout)

    def test_sys_exit_is_a_recorded_failure(self):
        location = self.launch("admin_ext_exit")
        with self.worker():
            state, response = self.wait_until_finished(location)
        self.assertEqual(state, "failed")
        self.assertContains(response, "SystemExit: exit code 3")
        self.assertContains(response, "about to exit with 3")

    def test_a_failing_command_is_reported_by_the_worker(self):
        location = self.launch("admin_ext_fail")
        with self.worker():
            state, response = self.wait_until_finished(location)
        self.assertEqual(state, "failed")
        self.assertContains(response, "CommandError: deliberate &lt;b&gt;failure&lt;/b&gt;")
        self.assertContains(response, "partial output before the failure")
        self.assertNotContains(response, "Traceback")

    def test_the_worker_revalidates_what_it_is_given(self):
        from django_extensions_admin.commands.tasks import run_command

        task = run_command.using(backend="commands")
        forged = [
            task.enqueue(key="flush", options={}, actor_id=str(self.user.pk)),
            task.enqueue(
                key="admin_ext_echo",
                options={"message": "x", "times": "99", "touch": "forged"},
                actor_id=str(self.user.pk),
            ),
            task.enqueue(
                key="admin_ext_prompt",  # needs a permission this user lacks
                options={},
                actor_id=str(self.user.pk),
            ),
        ]
        with self.worker():
            deadline = time.monotonic() + 60
            while DBTaskResult.objects.filter(status__in=["READY", "RUNNING"]).exists():
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.2)
        outcomes = [
            DBTaskResult.objects.get(id=result.id).exception_class_path.rsplit(".", 1)[1]
            for result in forged
        ]
        self.assertEqual(
            outcomes, ["CommandNotAllowed", "InvalidCommandOptions", "CommandNotAllowed"]
        )
        self.assertFalse(Device.objects.filter(name="forged").exists())

    def test_atomic_requests_launch_commits_before_the_worker_looks(self):
        with mock.patch.dict(connections.settings["default"], {"ATOMIC_REQUESTS": True}):
            location = self.launch(data={"message": "atomic", "times": "1", "touch": "atomic"})
        with self.worker():
            state, response = self.wait_until_finished(location)
        self.assertEqual(state, "succeeded")
        self.assertContains(response, "atomic\n")

    def test_a_pruned_result_is_unavailable(self):
        location = self.launch(data={"message": "soon gone", "times": "1"})
        with self.worker():
            self.assertEqual(self.wait_until_finished(location)[0], "succeeded")
        pruned = manage(
            SETTINGS,
            "prune_db_task_results",
            "--backend",
            "commands",
            "--queue-name",
            "*",
            "--min-age-days",
            "0",
        )
        self.assertIn("Deleted 1 task result", pruned.stdout)
        state, response = self.state(location)
        self.assertEqual((state, response.status_code), ("unavailable", 404))
        self.assertContains(response, "pruned or is unknown", status_code=404)
