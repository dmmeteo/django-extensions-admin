"""The command runner: explicit registrations, guarded pages, a worker that trusts nothing.

Tasks run through django-tasks-db's own worker loop in this process (``run_worker``);
``worker_tests`` repeats the journeys against a separately started ``db_worker``.
TransactionTestCase throughout the launch paths: TestCase holds every test inside
``atomic()``, which is exactly the state the launch view refuses.
"""

import json
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from unittest import mock

from django import forms
from django.contrib.auth.models import Permission, User
from django.core import signing
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections, transaction
from django.test import Client, SimpleTestCase, TransactionTestCase, override_settings
from django.urls import resolve
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from django_extensions_admin.commands import registry
from django_extensions_admin.commands.backend import CommandsUnavailable, get_backend, tasks_api
from django_extensions_admin.commands.checks import check_command_runner
from django_extensions_admin.commands.views import RESULT_SALT

from .testapp.admin import EchoForm, OptionsForm
from .testapp.models import Device

ROOT = Path(__file__).resolve().parent.parent
INDEX = "/admin/commands/"


def launch_url(name):
    return f"/admin/commands/{name}/"


def commands_setting(**values):
    return override_settings(ADMIN_EXTENSIONS={"COMMANDS_TASK_BACKEND": "commands", **values})


def run_worker():
    """Run every queued task here, as ``db_worker --batch`` would, without its signals."""
    from django_tasks_db.management.commands.db_worker import Worker

    Worker(
        queue_names=["default"],
        interval=0,
        batch=True,
        backend_name="commands",
        startup_delay=False,
        max_tasks=None,
        worker_id="in-process-test",
        excluded_queue_names=[],
    ).run()


def enqueue_directly(**kwargs):
    """What someone with database or code access could queue, bypassing the admin."""
    from django_extensions_admin.commands.tasks import run_command

    return run_command.using(backend="commands").enqueue(**kwargs)


class RunnerCase(TransactionTestCase):
    def setUp(self):
        self.root = User.objects.create_superuser("root", "root@example.invalid", "pw")
        self.runner = User.objects.create_user("run", "run@example.invalid", "pw", is_staff=True)
        self.runner.user_permissions.add(Permission.objects.get(codename="run_device_commands"))
        self.stranger = User.objects.create_user(
            "stranger", "stranger@example.invalid", "pw", is_staff=True
        )
        self.client.force_login(self.runner)

    def launch(self, name="admin_ext_echo", data=None, client=None):
        client = client or self.client
        if data is None:
            data = {"message": "hi", "times": "2"}
        return client.post(launch_url(name), data)

    def launch_ok(self, *args, **kwargs):
        response = self.launch(*args, **kwargs)
        self.assertEqual(response.status_code, 302, response.content[:2000])
        self.assertTrue(response["Location"].startswith("/admin/commands/results/"))
        return response["Location"]

    def sign(self, **reference):
        return f"/admin/commands/results/{signing.dumps(reference, salt=RESULT_SALT)}/"

    def only_run(self):
        self.assertEqual(DBTaskResult.objects.count(), 1)
        return DBTaskResult.objects.get()


class RegistrationTests(SimpleTestCase):
    def tearDown(self):
        registry._registry.pop("temporary", None)

    def test_a_command_is_registered_once(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "already registered"):
            registry.register("admin_ext_echo", permission="testapp.run_device_commands")

    def test_permission_is_required_and_dotted(self):
        for permission in (None, "", "run_device_commands", "testapp."):
            with self.subTest(permission=permission):
                with self.assertRaisesMessage(ImproperlyConfigured, "app_label.codename"):
                    registry.register("temporary", permission=permission)

    def test_uploads_cannot_reach_a_worker(self):
        class UploadForm(forms.Form):
            fixture = forms.FileField()

        with self.assertRaisesMessage(ImproperlyConfigured, "file field"):
            registry.register("temporary", permission="a.b", form=UploadForm)

    def test_the_runner_owns_output_and_prompting(self):
        class SneakyForm(forms.Form):
            interactive = forms.BooleanField(required=False)

        with self.assertRaisesMessage(ImproperlyConfigured, "set by the runner"):
            registry.register("temporary", permission="a.b", form=SneakyForm)

    def test_the_form_must_be_a_form_class(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "Django Form class"):
            registry.register("temporary", permission="a.b", form=EchoForm())

    def test_description_defaults_to_the_command_name(self):
        registration = registry.register("temporary", permission="a.b")
        self.assertEqual(registration.description, "Temporary")
        self.assertIs(registration.form, registry.NoOptionsForm)

    def test_values_that_change_on_a_second_validation_are_refused(self):
        class DriftingForm(forms.Form):
            message = forms.CharField()

            def clean_message(self):
                return object()

        form = DriftingForm(data={"message": "x"})
        self.assertTrue(form.is_valid())
        with self.assertRaises(registry.PayloadError):
            registry.build_payload(form)


class CheckTests(SimpleTestCase):
    def ids(self):
        return [message.id for message in check_command_runner()]

    def test_the_test_configuration_is_clean(self):
        self.assertEqual(check_command_runner(), [])

    def test_the_backend_alias_must_be_named(self):
        with override_settings(ADMIN_EXTENSIONS={}):
            self.assertEqual(self.ids(), ["django_extensions_admin.E101"])
            with self.assertRaisesMessage(CommandsUnavailable, "COMMANDS_TASK_BACKEND"):
                get_backend()

    def test_inline_or_missing_backends_are_refused(self):
        for alias, text in (
            ("missing", "not usable"),
            ("immediate", "ImmediateBackend"),
            ("dummy", "DummyBackend"),
        ):
            with self.subTest(alias=alias), commands_setting(COMMANDS_TASK_BACKEND=alias):
                self.assertEqual(self.ids(), ["django_extensions_admin.E101"])
                with self.assertRaisesMessage(CommandsUnavailable, text):
                    get_backend()

    def test_silencing_the_check_for_test_settings_still_refuses_to_run(self):
        from django.core import checks

        with (
            commands_setting(COMMANDS_TASK_BACKEND="dummy"),
            override_settings(SILENCED_SYSTEM_CHECKS=["django_extensions_admin.E101"]),
        ):
            reported = [m.id for m in checks.run_checks() if not m.is_silenced()]
            self.assertNotIn("django_extensions_admin.E101", reported)
            with self.assertRaisesMessage(CommandsUnavailable, "DummyBackend"):
                get_backend()

    def test_other_backends_are_unverified(self):
        with commands_setting(COMMANDS_TASK_BACKEND="unreachable"):
            self.assertEqual(self.ids(), ["django_extensions_admin.W101"])

    def test_unknown_commands_and_options_are_reported(self):
        class WrongForm(forms.Form):
            message = forms.CharField()
            colour = forms.CharField()

        registry.register("no_such_command", permission="a.b")
        registry._registry["wrong_form"] = registry.Registration(
            name="admin_ext_echo", permission="a.b", form=WrongForm, description="Wrong"
        )
        try:
            messages = check_command_runner()
        finally:
            registry._registry.pop("no_such_command")
            registry._registry.pop("wrong_form")
        self.assertEqual(
            [message.id for message in messages],
            ["django_extensions_admin.E103", "django_extensions_admin.E104"],
        )
        self.assertIn("colour", messages[1].msg)


class IsolationTests(SimpleTestCase):
    def test_installing_the_package_loads_no_task_machinery(self):
        """A fresh interpreter: the app installed and set up, the other features imported."""
        script = """
import sys
import django
from django.conf import settings
settings.configure(
    INSTALLED_APPS=["django_extensions_admin", "django.contrib.admin", "django.contrib.auth",
                    "django.contrib.contenttypes", "django.contrib.messages",
                    "django.contrib.sessions"],
    DATABASES={}, SECRET_KEY="x",
)
django.setup()
import django_extensions_admin
from django_extensions_admin import admin
loaded = sorted(m for m in sys.modules if m.startswith(
    ("django_extensions_admin.commands", "django_tasks", "django.tasks")))
print(loaded)
"""
        env = {**os.environ, "PYTHONPATH": f"{ROOT / 'src'}{os.pathsep}{ROOT}"}
        env.pop("DJANGO_SETTINGS_MODULE", None)
        output = subprocess.run(  # noqa: S603 - our own interpreter and script
            [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True
        ).stdout
        self.assertEqual(output.strip(), "[]")


@override_settings(ROOT_URLCONF="tests.urls_without_commands")
class NotIncludedTests(RunnerCase):
    def test_installing_the_app_routes_no_command_page(self):
        self.client.force_login(self.root)
        for url in (INDEX, launch_url("admin_ext_echo")):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {"message": "x"}).status_code, 404)
        self.assertEqual(DBTaskResult.objects.count(), 0)


class LaunchTests(RunnerCase):
    def test_index_lists_only_the_commands_the_user_may_run(self):
        response = self.client.get(INDEX)
        self.assertContains(response, launch_url("admin_ext_echo"))
        self.assertContains(response, launch_url("admin_ext_flood"))
        self.assertNotContains(response, launch_url("admin_ext_prompt"))
        self.client.force_login(self.stranger)
        self.assertContains(self.client.get(INDEX), "no commands you have permission to run")

    def test_pages_need_an_admin_login(self):
        civilian = User.objects.create_user("civilian", "c@example.invalid", "pw")
        civilian.user_permissions.add(Permission.objects.get(codename="run_device_commands"))
        not_staff = Client()
        not_staff.force_login(civilian)
        for client in (Client(), not_staff):
            for url in (INDEX, launch_url("admin_ext_echo")):
                response = client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])
            self.assertEqual(self.launch(client=client).status_code, 302)
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_the_form_page_is_permission_checked(self):
        response = self.client.get(launch_url("admin_ext_echo"))
        self.assertContains(response, 'name="message"')
        self.assertContains(response, 'value="Run"')
        self.assertContains(response, "Echo a message a few times.")
        self.assertEqual(self.client.get(launch_url("admin_ext_prompt")).status_code, 403)
        self.assertEqual(self.client.get(launch_url("migrate")).status_code, 404)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(launch_url("admin_ext_echo")).status_code, 403)

    def test_a_command_without_options_still_needs_a_post(self):
        self.client.force_login(self.root)
        response = self.client.get(launch_url("admin_ext_prompt"))
        self.assertContains(response, "This command takes no options.")
        self.assertContains(response, 'value="Run"')

    def test_get_never_launches(self):
        response = self.client.get(launch_url("admin_ext_echo"), {"message": "x", "touch": "t"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DBTaskResult.objects.count(), 0)
        for method in ("put", "delete", "patch"):
            self.assertEqual(
                getattr(self.client, method)(launch_url("admin_ext_echo")).status_code, 405
            )
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_launch_needs_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.runner)
        self.assertEqual(self.launch(client=client).status_code, 403)
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_denied_and_unknown_posts_queue_nothing(self):
        self.assertEqual(self.launch("admin_ext_prompt", {}).status_code, 403)
        self.assertEqual(self.launch("migrate", {}).status_code, 404)
        self.assertEqual(self.launch("../admin_ext_echo", {}).status_code, 404)
        self.client.force_login(self.stranger)
        self.assertEqual(self.launch().status_code, 403)
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_invalid_options_are_shown_and_queue_nothing(self):
        response = self.launch(data={"message": "", "times": "9"})
        self.assertContains(response, "Please correct the errors below.")
        self.assertContains(response, "errorlist")
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_a_valid_post_queues_one_run_and_redirects_to_its_signed_result(self):
        device = Device.objects.create(name="alpha")
        location = self.launch_ok(
            data={"message": "hi", "times": "2", "device": str(device.pk), "junk": "ignored"}
        )
        run = self.only_run()
        self.assertEqual(run.backend_name, "commands")
        self.assertEqual(run.status, "READY")
        self.assertEqual(
            run.args_kwargs,
            {
                "args": [],
                "kwargs": {
                    "key": "admin_ext_echo",
                    # Submitted values, not objects: the worker validates them itself.
                    "options": {
                        "message": "hi",
                        "times": "2",
                        "touch": None,
                        "device": str(device.pk),
                    },
                    # A string, so any primary key type is JSON.
                    "actor_id": str(self.runner.pk),
                },
            },
        )
        token = location.rstrip("/").rsplit("/", 1)[1]
        self.assertEqual(
            signing.loads(token, salt=RESULT_SALT),
            {"id": str(run.id), "b": "commands", "c": "admin_ext_echo", "u": str(self.runner.pk)},
        )
        self.assertContains(self.client.get(location), "Queued “Echo”.")


class TransactionTests(RunnerCase):
    databases = {"default", "other"}

    def test_the_launch_view_opts_out_of_atomic_requests_for_every_database(self):
        match = resolve(launch_url("admin_ext_echo"))
        self.assertEqual(match.func._non_atomic_requests, {"default", "other"})
        # The pages that only read keep the project's transaction policy.
        self.assertFalse(hasattr(resolve(INDEX).func, "_non_atomic_requests"))

    def test_atomic_requests_on_every_database_still_launch_and_commit(self):
        with (
            mock.patch.dict(connections.settings["default"], {"ATOMIC_REQUESTS": True}),
            mock.patch.dict(connections.settings["other"], {"ATOMIC_REQUESTS": True}),
        ):
            location = self.launch_ok()
            self.assertContains(self.client.get(location), "Queued")
        self.only_run()
        run_worker()
        self.assertEqual(self.only_run().status, "SUCCESSFUL")

    @override_settings(
        MIDDLEWARE=[
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "tests.testapp.middleware.OuterTransactionMiddleware",
        ]
    )
    def test_an_outer_transaction_is_refused_rather_than_deferred(self):
        response = self.launch(data={"message": "hi", "times": "1", "touch": "deferred"})
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "open database transaction", status_code=503)
        self.assertNotContains(response, "Queued", status_code=503)
        # The outer block has committed by now; nothing was waiting for it.
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_a_rolled_back_transaction_publishes_nothing(self):
        from django_extensions_admin.commands.tasks import enqueue_on_commit

        payload = {"message": "hi", "times": "1", "touch": "rolled-back"}
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.assertIsNone(
                enqueue_on_commit("admin_ext_echo", payload, self.root.pk, "commands")
            )
            raise RuntimeError("roll back")
        self.assertEqual(DBTaskResult.objects.count(), 0)

        with transaction.atomic():
            self.assertIsNone(
                enqueue_on_commit("admin_ext_echo", payload, self.root.pk, "commands")
            )
            self.assertEqual(DBTaskResult.objects.count(), 0)
        self.only_run()

        result = enqueue_on_commit("admin_ext_echo", payload, self.root.pk, "commands")
        self.assertEqual(str(result.id), str(DBTaskResult.objects.latest("enqueued_at").id))


class BackendFailureTests(RunnerCase):
    def test_misconfigured_backends_never_run_anything_inline(self):
        for alias in (None, "missing", "immediate", "dummy"):
            with self.subTest(alias=alias), commands_setting(COMMANDS_TASK_BACKEND=alias):
                self.assertContains(self.client.get(INDEX), 'class="error"')
                form = self.client.get(launch_url("admin_ext_echo"))
                self.assertContains(form, 'class="error"')
                self.assertNotContains(form, 'value="Run"')
                response = self.launch(data={"message": "x", "times": "1", "touch": "inline"})
                self.assertEqual(response.status_code, 503)
                self.assertContains(response, "Nothing was queued", status_code=503)
                self.assertNotContains(response, "Queued “", status_code=503)
        self.assertFalse(Device.objects.filter(name="inline").exists())
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_an_enqueue_failure_is_visible_and_claims_nothing(self):
        """Honest either way: the backend may or may not have stored the run."""
        with (
            mock.patch(
                "django_tasks_db.backend.DatabaseBackend.enqueue",
                side_effect=DatabaseError("queue table is locked"),
            ),
            self.assertLogs("django_extensions_admin.commands", "ERROR"),
        ):
            response = self.launch()
        self.assertEqual(response.status_code, 503)
        self.assertContains(
            response,
            "may not have been queued: the task backend raised DatabaseError",
            status_code=503,
        )
        self.assertContains(response, "check before running the command again", status_code=503)
        self.assertNotContains(response, "Nothing was queued", status_code=503)
        self.assertNotContains(response, "Queued “", status_code=503)
        self.assertEqual(DBTaskResult.objects.count(), 0)

    def test_a_failure_after_the_backend_stored_the_run_does_not_deny_it(self):
        """django-tasks-db inserts the row, then sends task_enqueued with send(), so a
        receiver that raises fails the enqueue after the run was stored - and it runs."""
        task_enqueued = import_module(f"{tasks_api().module}.signals").task_enqueued

        def broken_receiver(**kwargs):
            raise RuntimeError("a project's receiver failed")

        task_enqueued.connect(broken_receiver, dispatch_uid="admin-ext-test-broken")
        self.addCleanup(task_enqueued.disconnect, dispatch_uid="admin-ext-test-broken")
        with self.assertLogs("django_extensions_admin.commands", "ERROR"):
            response = self.launch(data={"message": "hi", "times": "1", "touch": "stored"})
        self.assertContains(
            response,
            "may not have been queued: the task backend raised RuntimeError",
            status_code=503,
        )
        self.assertContains(response, "a worker will still run it", status_code=503)
        self.assertNotContains(response, "Nothing was queued", status_code=503)
        self.assertEqual(self.only_run().status, "READY")  # stored, and it will run
        run_worker()
        self.assertTrue(Device.objects.filter(name="stored").exists())

    def test_an_unreachable_queue_is_visible(self):
        with (
            commands_setting(COMMANDS_TASK_BACKEND="unreachable"),
            self.assertLogs("django_extensions_admin.commands", "ERROR"),
        ):
            response = self.launch()
        self.assertContains(response, "the task backend raised ConnectionError", status_code=503)


class ResultTests(RunnerCase):
    def test_the_initiator_sees_the_output_once_the_worker_ran(self):
        location = self.launch_ok(data={"message": "hi", "times": "2", "touch": "made-by-worker"})
        self.assertFalse(Device.objects.filter(name="made-by-worker").exists())
        run_worker()
        self.assertTrue(Device.objects.filter(name="made-by-worker").exists())
        response = self.client.get(location)
        self.assertContains(response, 'data-state="succeeded"')
        self.assertContains(response, "hi\nhi\n")
        self.assertContains(response, "done")  # stderr
        self.assertNotContains(response, 'http-equiv="refresh"')

    def test_a_pending_run_refreshes_itself_without_javascript(self):
        location = self.launch_ok()
        response = self.client.get(location)
        self.assertContains(response, 'data-state="queued"')
        self.assertContains(response, '<meta http-equiv="refresh" content="3">')
        self.assertContains(response, ">Refresh</a>")
        DBTaskResult.objects.update(status="RUNNING", started_at=timezone.now())
        self.assertContains(self.client.get(location), 'data-state="running"')

    def test_a_stale_run_warns_and_stops_refreshing(self):
        location = self.launch_ok()
        long_ago = timezone.now() - timedelta(hours=2)
        DBTaskResult.objects.update(enqueued_at=long_ago)
        response = self.client.get(location)
        self.assertContains(response, "Still queued after 120 minutes")
        self.assertContains(response, "&#x27;commands&#x27;")
        self.assertNotContains(response, 'http-equiv="refresh"')
        DBTaskResult.objects.update(status="RUNNING", started_at=long_ago)
        response = self.client.get(location)
        self.assertContains(response, "the worker may have stopped")
        self.assertContains(response, "not retried automatically")
        self.assertNotContains(response, 'http-equiv="refresh"')
        with commands_setting(COMMANDS_STALE_AFTER=3 * 3600):
            self.assertContains(self.client.get(location), 'http-equiv="refresh"')

    def test_a_failed_command_shows_its_error_and_output_but_no_traceback(self):
        location = self.launch_ok("admin_ext_fail", {})
        with self.assertLogs("django_extensions_admin.commands", "ERROR") as logged:
            run_worker()
        # The original exception, frames and all, goes to the worker's log.
        self.assertIn("CommandError: deliberate <b>failure</b>", logged.output[0])
        self.assertTrue(self.only_run().traceback.startswith("Traceback"))
        response = self.client.get(location)
        self.assertContains(response, 'data-state="failed"')
        self.assertContains(response, "CommandError: deliberate &lt;b&gt;failure&lt;/b&gt;")
        self.assertContains(response, "partial output before the failure")
        self.assertNotContains(response, "Traceback")
        self.assertNotContains(response, "<b>failure</b>")

    @commands_setting(COMMANDS_OUTPUT_LIMIT=500)
    def test_output_is_bounded_and_escaped(self):
        location = self.launch_ok("admin_ext_flood", {"chars": "5000"})
        run_worker()
        value = self.only_run().return_value
        self.assertEqual(len(value["stdout"]), 500)
        self.assertTrue(value["truncated"])
        response = self.client.get(location)
        self.assertContains(response, "Output was cut after 500 characters.")
        self.assertContains(response, "&lt;script&gt;window.__pwned = 1&lt;/script&gt;")
        self.assertNotContains(response, "<script>window.__pwned")
        self.assertNotContains(response, 'onerror="alert(1)"')
        self.assertNotContains(response, "THE-END")

    def test_the_page_bounds_what_a_backend_returns(self):
        location = self.launch_ok()
        DBTaskResult.objects.update(
            status="SUCCESSFUL", finished_at=timezone.now(), return_value={"stdout": "y" * 30_000}
        )
        response = self.client.get(location)
        self.assertContains(response, "Output was cut after 20000 characters.")
        self.assertNotContains(response, "y" * 20_001)

    def test_prompting_commands_are_told_not_to(self):
        self.client.force_login(self.root)
        location = self.launch_ok("admin_ext_prompt", {})
        run_worker()
        self.assertContains(self.client.get(location), "interactive=False")

    def test_model_choices_are_looked_up_again_in_the_worker(self):
        device = Device.objects.create(name="alpha")
        location = self.launch_ok(data={"message": "m", "times": "1", "device": str(device.pk)})
        run_worker()
        self.assertContains(self.client.get(location), "device=alpha")


class ReferenceTests(RunnerCase):
    def setUp(self):
        super().setUp()
        self.location = self.launch_ok()
        self.run = self.only_run()

    def reference(self, **changes):
        return self.sign(
            **{
                "id": str(self.run.id),
                "b": "commands",
                "c": "admin_ext_echo",
                "u": str(self.runner.pk),
            }
            | changes
        )

    def test_forged_references_do_not_exist(self):
        token = self.location.rstrip("/").rsplit("/", 1)[1]
        for url in (
            "/admin/commands/results/garbage/",
            f"/admin/commands/results/{token[:-2]}xx/",
            f"/admin/commands/results/{self.run.id}/",
            "/admin/commands/results/"
            + signing.dumps({"id": str(self.run.id), "u": str(self.runner.pk)}, salt="other")
            + "/",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_another_users_reference_does_not_exist_even_for_a_superuser(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get(self.location).status_code, 404)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(self.location).status_code, 404)

    def test_permission_is_checked_again_when_reading(self):
        self.runner.user_permissions.clear()
        self.client.force_login(User.objects.get(pk=self.runner.pk))
        self.assertEqual(self.client.get(self.location).status_code, 403)

    def test_an_unregistered_command_has_no_result_page(self):
        self.assertEqual(self.client.get(self.reference(c="migrate")).status_code, 404)

    def test_a_pruned_result_is_unavailable(self):
        DBTaskResult.objects.all().delete()
        response = self.client.get(self.location)
        self.assertContains(response, 'data-state="unavailable"', status_code=404)
        self.assertContains(response, "pruned or is unknown", status_code=404)

    def test_a_result_from_another_backend_is_unavailable(self):
        with commands_setting(COMMANDS_TASK_BACKEND="unreachable"):
            response = self.client.get(self.location)
        self.assertContains(response, "no longer the one configured", status_code=404)
        with commands_setting(COMMANDS_TASK_BACKEND="dummy"):
            response = self.client.get(self.location)
        self.assertContains(response, "DummyBackend", status_code=503)

    def test_the_stored_run_must_corroborate_the_reference(self):
        self.client.force_login(self.root)
        self.assertEqual(self.client.get(self.reference(u=str(self.root.pk))).status_code, 404)
        with self.assertLogs("django_extensions_admin.commands", "WARNING"):
            response = self.client.get(self.reference(u=str(self.root.pk)))
        self.assertContains(response, 'data-state="unavailable"', status_code=404)
        self.client.force_login(self.runner)
        with self.assertLogs("django_extensions_admin.commands", "WARNING"):
            response = self.client.get(self.reference(c="admin_ext_flood"))
        self.assertContains(response, 'data-state="unavailable"', status_code=404)


class WorkerRevalidationTests(RunnerCase):
    """Whatever reaches the queue, the worker checks the registry, user and options again."""

    def failure_of(self, result):
        run_worker()
        run = DBTaskResult.objects.get(id=result.id)
        self.assertEqual(run.status, "FAILED")
        details = json.loads(run.traceback.rsplit(f"{run.exception_class_path}: ", 1)[1])
        return run.exception_class_path.rsplit(".", 1)[1], details["error"]

    def test_an_unregistered_key_is_refused(self):
        result = enqueue_directly(key="flush", options={}, actor_id=self.root.pk)
        self.assertEqual(
            self.failure_of(result),
            ("CommandNotAllowed", "'flush' is not a registered admin command in this worker."),
        )

    def test_a_registration_removed_since_launch_is_refused(self):
        self.launch_ok(data={"message": "hi", "times": "1", "touch": "unregistered"})
        registration = registry._registry.pop("admin_ext_echo")
        try:
            name, _ = self.failure_of(self.only_run())
        finally:
            registry._registry["admin_ext_echo"] = registration
        self.assertEqual(name, "CommandNotAllowed")
        self.assertFalse(Device.objects.filter(name="unregistered").exists())

    def test_invalid_options_are_refused(self):
        options = {"message": "x", "times": "99", "touch": "invalid"}
        result = enqueue_directly(key="admin_ext_echo", options=options, actor_id=self.root.pk)
        name, error = self.failure_of(result)
        self.assertEqual(name, "InvalidCommandOptions")
        self.assertIn("times", error)
        result = enqueue_directly(
            key="admin_ext_echo", options="--settings=x", actor_id=self.root.pk
        )
        self.assertEqual(self.failure_of(result)[0], "InvalidCommandOptions")
        self.assertFalse(Device.objects.filter(name="invalid").exists())

    def test_the_actor_must_still_be_allowed(self):
        options = {"message": "x", "times": "1", "touch": "actor"}
        inactive = User.objects.create_superuser(
            "gone", "gone@example.invalid", "pw", is_active=False
        )
        not_staff = User.objects.create_user("former", "former@example.invalid", "pw")
        not_staff.user_permissions.add(Permission.objects.get(codename="run_device_commands"))
        for actor_id in (
            self.stranger.pk,  # staff, no permission
            str(not_staff.pk),  # permission, but no longer staff
            inactive.pk,
            987654,
            str(uuid.uuid4()),  # not a key of this user model at all
            None,
        ):
            with self.subTest(actor_id=actor_id):
                result = enqueue_directly(key="admin_ext_echo", options=options, actor_id=actor_id)
                self.assertEqual(self.failure_of(result)[0], "CommandNotAllowed")
        self.assertFalse(Device.objects.filter(name="actor").exists())

    def test_losing_staff_status_while_queued_stops_the_run(self):
        location = self.launch_ok(data={"message": "hi", "times": "1", "touch": "unstaffed"})
        User.objects.filter(pk=self.runner.pk).update(is_staff=False)
        run_worker()
        self.assertEqual(self.only_run().status, "FAILED")
        self.assertFalse(Device.objects.filter(name="unstaffed").exists())
        User.objects.filter(pk=self.runner.pk).update(is_staff=True)
        self.assertContains(self.client.get(location), "may no longer run it")

    def test_the_actor_travels_as_a_string_through_the_worker(self):
        from django_extensions_admin.commands.tasks import enqueue_on_commit

        result = enqueue_on_commit(
            "admin_ext_echo", {"message": "s", "times": "1"}, str(self.runner.pk), "commands"
        )
        run_worker()
        self.assertEqual(DBTaskResult.objects.get(id=result.id).status, "SUCCESSFUL")
        # A UUID key is JSON as a string; enqueueing the UUID object itself would fail.
        stored = enqueue_on_commit("admin_ext_echo", {}, str(uuid.uuid4()), "commands")
        self.assertEqual(DBTaskResult.objects.get(id=stored.id).status, "READY")
        with self.assertRaises(TypeError):
            enqueue_on_commit("admin_ext_echo", {}, uuid.uuid4(), "commands")

    def test_a_launched_run_that_the_worker_refuses_shows_why(self):
        location = self.launch_ok()
        self.runner.user_permissions.clear()
        run_worker()
        self.runner.user_permissions.add(Permission.objects.get(codename="run_device_commands"))
        self.client.force_login(User.objects.get(pk=self.runner.pk))
        response = self.client.get(location)
        self.assertContains(response, 'data-state="failed"')
        self.assertContains(response, "may no longer run it")


class OptionTests(RunnerCase):
    """Ordinary Django fields reach the command with their meaning intact."""

    def setUp(self):
        super().setUp()
        self.alpha = Device.objects.create(name="alpha")
        self.beta = Device.objects.create(name="beta")

    def filled(self):
        return {
            "limit": "0",  # a meaningful zero is passed, not treated as blank
            "label": "nightly",
            "dry_run": "on",
            "kinds": ["sensor", "relay"],
            "devices": [str(self.alpha.pk), str(self.beta.pk)],
            "when_0": "2026-09-24",
            "when_1": "10:30:00",
        }

    def output(self, data):
        location = self.launch_ok("admin_ext_options", data)
        run_worker()
        response = self.client.get(location)
        self.assertContains(response, 'data-state="succeeded"')
        return response.context["stdout"].splitlines()

    def test_multi_value_fields_survive_the_second_validation(self):
        form = OptionsForm(data=self.filled())
        self.assertTrue(form.is_valid(), form.errors)
        payload = registry.build_payload(form)
        # Keyed as the widgets read them: the split date/time as its two sub-inputs.
        self.assertEqual(payload["when_0"], "2026-09-24")
        self.assertEqual(payload["when_1"], "10:30:00")
        self.assertEqual(payload["devices"], [str(self.alpha.pk), str(self.beta.pk)])
        self.assertEqual(payload["kinds"], ["sensor", "relay"])
        again = OptionsForm(data=payload)
        self.assertTrue(again.is_valid(), again.errors)
        self.assertEqual(list(again.cleaned_data["devices"]), [self.alpha, self.beta])

    def test_filled_options_reach_the_command(self):
        self.assertEqual(
            self.output(self.filled()),
            [
                "limit=0",
                "label='nightly'",
                "dry_run=True",
                "kinds=['sensor', 'relay']",
                "devices=['alpha', 'beta']",
                # Read in the active time zone, as the admin's own split widget is.
                f"when={timezone.make_aware(datetime(2026, 9, 24, 10, 30)).isoformat()!r}",
            ],
        )

    def test_blank_optional_fields_leave_the_command_defaults_alone(self):
        self.assertEqual(
            self.output({}),
            [
                "limit=100",
                "label='untitled'",
                "dry_run=False",
                "kinds=['all']",
                "devices=None",
                "when=None",
            ],
        )

    def test_an_unticked_boolean_is_still_passed_as_false(self):
        form = OptionsForm(data={})
        self.assertTrue(form.is_valid())
        self.assertEqual(registry.command_arguments(form), {"dry_run": False})


class FailureRecordTests(RunnerCase):
    """What the backend stores about a failure is bounded, whatever the command raised."""

    def test_a_huge_exception_message_is_not_stored(self):
        location = self.launch_ok("admin_ext_fail", {"padding": "1000000"})
        with self.assertLogs("django_extensions_admin.commands", "ERROR"):
            run_worker()
        run = self.only_run()
        self.assertEqual(run.status, "FAILED")
        self.assertLess(len(run.traceback), 10_000)
        self.assertNotIn("direct cause", run.traceback)
        self.assertNotIn("CommandError(", run.traceback)
        response = self.client.get(location)
        self.assertContains(response, "CommandError: deliberate &lt;b&gt;failure&lt;/b&gt;!!!")
        self.assertContains(response, "partial output before the failure")

    def test_sys_exit_fails_the_run_with_its_code_and_output(self):
        location = self.launch_ok("admin_ext_exit", {})
        with self.assertLogs("django_extensions_admin.commands", "ERROR"):
            run_worker()
        self.assertEqual(self.only_run().exception_class_path.rsplit(".", 1)[1], "CommandFailed")
        response = self.client.get(location)
        self.assertContains(response, 'data-state="failed"')
        self.assertContains(response, "SystemExit: exit code 3")
        self.assertContains(response, "about to exit with 3")

    def test_a_zero_exit_is_a_success(self):
        location = self.launch_ok("admin_ext_exit", {"code": "0"})
        run_worker()
        response = self.client.get(location)
        self.assertContains(response, 'data-state="succeeded"')
        self.assertContains(response, "about to exit with 0")

    def test_the_workers_own_shutdown_is_not_swallowed(self):
        """A second SIGTERM makes db_worker raise SystemExit from its signal handler,
        wherever the command happens to be. That must still end the worker."""
        from django_tasks_db.management.commands.db_worker import Worker

        from django_extensions_admin.commands.tasks import run_command

        saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        self.addCleanup(lambda: [signal.signal(sig, h) for sig, h in saved.items()])
        worker = Worker(
            queue_names=["default"],
            interval=0,
            batch=True,
            backend_name="commands",
            startup_delay=False,
            max_tasks=None,
            worker_id="shutdown-test",
            excluded_queue_names=[],
        )
        worker.running = False  # the first signal has already arrived

        def interrupted(*args, **kwargs):
            worker.shutdown(signal.SIGTERM, None)

        with (
            mock.patch(
                "tests.testapp.management.commands.admin_ext_echo.Command.handle",
                side_effect=interrupted,
            ),
            self.assertRaises(SystemExit) as caught,
        ):
            run_command.func("admin_ext_echo", {"message": "m", "times": "1"}, str(self.root.pk))
        self.assertEqual(caught.exception.code, 1)
