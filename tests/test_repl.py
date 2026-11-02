"""The REPL tool: settings, real PTY sessions, and who may reach them over HTTP and WebSocket."""

import importlib.util
import json
import re
import struct
import time
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.apps import apps
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TransactionTestCase, override_settings

from django_extensions_admin.repl.checks import check_repl
from django_extensions_admin.repl.conf import Facts, get_config
from django_extensions_admin.repl.sessions import (
    OutputLog,
    ReplUnavailable,
    SessionManager,
    State,
    manager,
)

from .asgi import application
from .repl_support import StartedSessions, alive, screen, wait_for, wait_output

STREAM = "/admin/repl/stream/"
WITH_IPYTHON = Facts(ipython=True, django_extensions=False)
BARE = Facts(ipython=False, django_extensions=False)
EVERYTHING = Facts(ipython=True, django_extensions=True)


def repl_settings(**values):
    from django.conf import settings

    return override_settings(
        ADMIN_EXTENSIONS={**settings.ADMIN_EXTENSIONS, "REPL_ENABLED": True, **values}
    )


class ConfigTests(SimpleTestCase):
    def test_auto_backend_prefers_ipython_and_falls_back_to_plain_python(self):
        config = get_config()
        self.assertEqual(
            config.default_backend(WITH_IPYTHON).argv, ("shell", "--interface", "ipython")
        )
        self.assertEqual(config.default_backend(BARE).argv, ("shell", "--interface", "python"))
        self.assertEqual(list(config.offered(BARE)), ["python"])
        self.assertEqual(config.offered(EVERYTHING)["shell_plus"].argv, ("shell_plus", "--ipython"))
        plain = Facts(ipython=False, django_extensions=True)
        self.assertEqual(config.offered(plain)["shell_plus"].argv, ("shell_plus", "--plain"))

    @repl_settings(REPL_BACKEND="python", REPL_ALLOWED_BACKENDS=["python", "ipython"])
    def test_allowed_backends_limit_what_the_browser_is_offered(self):
        config = get_config()
        self.assertEqual(list(config.offered(EVERYTHING)), ["python", "ipython"])
        self.assertEqual(config.default_backend(EVERYTHING).key, "python")

    @repl_settings(REPL_BACKEND="shell_plus")
    def test_explicit_unavailable_backend_is_reported_not_silently_replaced(self):
        self.assertEqual(
            get_config().problems(WITH_IPYTHON),
            ["ADMIN_EXTENSIONS['REPL_BACKEND'] = 'shell_plus' is not available here."],
        )
        self.assertIsNone(get_config().default_backend(WITH_IPYTHON))

    def test_off_by_default_and_a_disabled_repl_reports_nothing(self):
        self.assertFalse(get_config().enabled)
        with override_settings(ADMIN_EXTENSIONS={"REPL_BACKEND": "shell_plus"}):
            self.assertEqual(check_repl(None), [])

    def test_invalid_settings_fail_the_system_check(self):
        cases = [
            (
                {"REPL_IDLE_TIMEOUT": 0},
                "ADMIN_EXTENSIONS['REPL_IDLE_TIMEOUT'] must be a positive integer, got 0.",
            ),
            (
                {"REPL_BACKEND": "bash"},
                "ADMIN_EXTENSIONS['REPL_BACKEND'] must be 'auto' or one of python, ipython,"
                " shell_plus, got 'bash'.",
            ),
            (
                {"REPL_ENABLED": "yes"},
                "ADMIN_EXTENSIONS['REPL_ENABLED'] must be True or False, got 'yes'.",
            ),
            (
                {"REPL_STREAM_PATH": "ws"},
                "ADMIN_EXTENSIONS['REPL_STREAM_PATH'] must start and end with '/'.",
            ),
        ]
        for raw, message in cases:
            with self.subTest(raw=raw), override_settings(ADMIN_EXTENSIONS=raw):
                self.assertEqual(
                    [(e.id, e.msg) for e in check_repl(None)],
                    [("django_extensions_admin.E501", message)],
                )

    def test_an_enabled_repl_refuses_a_wildcard_allowed_hosts(self):
        with repl_settings(), override_settings(ALLOWED_HOSTS=["*"]):
            self.assertIn("django_extensions_admin.E503", [e.id for e in check_repl(None)])
        with repl_settings():
            self.assertNotIn("django_extensions_admin.E503", [e.id for e in check_repl(None)])

    def test_the_websocket_route_carries_its_own_origin_check(self):
        from channels.security.websocket import OriginValidator

        from django_extensions_admin.repl.routing import websocket_urlpatterns

        self.assertIsInstance(websocket_urlpatterns[0].callback, OriginValidator)

    @repl_settings(REPL_BACKEND="shell_plus")
    def test_an_enabled_repl_reports_an_unavailable_backend(self):
        if apps.is_installed("django_extensions"):
            self.skipTest("django-extensions is installed in this lane, so shell_plus is available")
        self.assertEqual(
            [(e.id, e.msg) for e in check_repl(None)],
            [
                (
                    "django_extensions_admin.E502",
                    "ADMIN_EXTENSIONS['REPL_BACKEND'] = 'shell_plus' is not available here.",
                )
            ],
        )


class SessionTests(SimpleTestCase):
    def setUp(self):
        self.sessions = StartedSessions(self)

    def test_output_log_trims_at_a_line_boundary_and_exposes_the_gap(self):
        log = OutputLog(limit=10)
        log.append(b"aaaa\nbbbb\ncccc\n")
        self.assertEqual((log.start, log.end), (10, 15))
        self.assertEqual(log.read(0), (10, b"cccc\n"))
        self.assertEqual(log.read(12), (12, b"cc\n"))
        self.assertEqual(log.read(15), (15, b""))

    def test_cold_builtin_python_runs_real_code_with_the_requested_terminal_size(self):
        session = self.sessions.start("python")
        wait_output(session, ">>> ")
        self.assertTrue(session.resize(91, 27))
        session.write(b"import os; print(sum(range(10)) * 7, os.get_terminal_size(0))\r")
        wait_output(session, "315 os.terminal_size(columns=91, lines=27)")

    def test_ctrl_c_interrupts_running_code_without_killing_the_repl(self):
        session = self.sessions.start("python")
        wait_output(session, ">>> ")
        session.write(b"import time; time.sleep(60)\r")
        time.sleep(0.5)
        session.write(b"\x03")
        wait_output(session, "KeyboardInterrupt", timeout=5)
        session.write(b"print(6 * 7 * 11)\r")
        wait_output(session, "462")
        self.assertIs(session.state, State.RUNNING)

    def test_offered_backends_follow_what_is_installed(self):
        offered = get_config().offered(Facts.observe())
        self.assertEqual("ipython" in offered, importlib.util.find_spec("IPython") is not None)
        self.assertEqual("shell_plus" in offered, apps.is_installed("django_extensions"))
        self.assertEqual(offered["python"].argv, ("shell", "--interface", "python"))

    def test_optional_backends_start_real_interpreters_with_models_loaded(self):
        offered = get_config().offered(Facts.observe())
        for backend in ("ipython", "shell_plus"):
            with self.subTest(backend=backend):
                if backend not in offered:
                    self.skipTest(f"{backend} is not installed in this lane")
                session = self.sessions.start(backend)
                wait_output(session, "In [")
                session.write(b"print(Device.__name__ * 3)\r")
                wait_output(session, "DeviceDeviceDevice")

    def test_end_kills_the_process_tree_and_permits_a_fresh_session(self):
        session = self.sessions.start("python")
        wait_output(session, ">>> ")
        session.write(
            b"import subprocess; a = subprocess.Popen(['sleep', '300']); "
            b"b = subprocess.Popen(['sleep', '301'], start_new_session=True); "
            b"print('pids', a.pid, b.pid, sep=':')\r"
        )
        child, escaped = map(
            int, re.search(r"pids:(\d+):(\d+)", wait_output(session, "pids:")).groups()
        )
        self.assertTrue(alive(session.pid) and alive(child) and alive(escaped))

        manager.end(session.owner_id)

        self.assertIs(session.state, State.ENDED)
        self.assertEqual(session.reason, "Ended by the user.")
        self.assertFalse(session.write(b"print('late')\r"))
        self.assertFalse(session.resize(100, 30))
        wait_for(lambda: not any(alive(pid) for pid in (session.pid, child, escaped)), timeout=5)
        fresh, created = manager.start(session.owner_id, session.backend, get_config())
        self.assertTrue(created)
        self.assertNotEqual((fresh.id, fresh.pid), (session.id, session.pid))

    def test_process_exit_is_reported_with_its_code(self):
        session = self.sessions.start("python")
        wait_output(session, ">>> ")
        session.write(b"raise SystemExit(3)\r")
        wait_for(lambda: session.state is State.EXITED, timeout=10)
        self.assertEqual(session.exit_code, 3)
        self.assertEqual(session.reason, "The REPL process exited with code 3.")

    def test_idle_expiry_counts_input_but_not_attached_viewers(self):
        session = self.sessions.start("python", idle_timeout=3)
        deadline = time.monotonic() + 30
        while ">>> " not in screen(session):
            self.assertLess(time.monotonic(), deadline)
            session.write(b"\r")
            time.sleep(0.5)
            self.assertIs(session.state, State.RUNNING)
        for _ in range(5):
            time.sleep(1)
            self.assertIs(session.state, State.RUNNING)
            session.write(b"\r")

        session.subscribe(lambda: None)
        deadline = time.monotonic() + 8
        while session.state is State.RUNNING and time.monotonic() < deadline:
            session.read(0)
            time.sleep(0.1)

        self.assertIs(session.state, State.EXPIRED)
        self.assertEqual(session.reason, "No input for 3 s; the idle limit ended the process.")
        wait_for(lambda: not alive(session.pid), timeout=5)

    def test_a_second_server_process_cannot_host_sessions(self):
        self.sessions.start("python")
        config = get_config()
        with self.assertRaisesRegex(ReplUnavailable, "single ASGI server process"):
            SessionManager().start(1, config.offered(Facts.observe())["python"], config)


def client_for(user=None, **kwargs):
    client = Client(**kwargs)
    if user is not None:
        client.force_login(user)
    return client


def post_json(client, url, payload=None):
    return client.post(url, json.dumps(payload or {}), content_type="application/json")


def ws_headers(user=None, origin=b"http://localhost"):
    headers = [(b"origin", origin)]
    if user is not None:
        headers.append(
            (b"cookie", f"sessionid={client_for(user).cookies['sessionid'].value}".encode())
        )
    return headers


async def connect(headers):
    communicator = WebsocketCommunicator(application, STREAM, headers=headers)
    connected, code = await communicator.connect(timeout=5)
    return communicator, connected, code


async def rejected(headers):
    communicator, connected, code = await connect(headers)
    await communicator.wait()
    return connected, code


@repl_settings()
class AccessTests(TransactionTestCase):
    def setUp(self):
        def make(username, **flags):
            flags.setdefault("is_staff", True)
            return User.objects.create_user(username, password="pw", **flags)

        self.users = {
            "owner": make("owner", is_superuser=True),
            "other": make("other", is_superuser=True),
            "staff": make("staff"),
            "inactive": make("inactive", is_superuser=True, is_active=False),
            "nonstaff": make("nonstaff", is_superuser=True, is_staff=False),
        }
        for user in self.users.values():
            self.addCleanup(manager.end, user.pk)

    def test_only_active_staff_superusers_reach_control_endpoints(self):
        expectations = {None: 401, "staff": 403, "inactive": 401, "nonstaff": 403}
        for name, status in expectations.items():
            with self.subTest(user=name):
                client = client_for(self.users.get(name))
                self.assertEqual(client.get("/admin/repl/state/").status_code, status)
                self.assertEqual(post_json(client, "/admin/repl/start/").status_code, status)
                self.assertEqual(post_json(client, "/admin/repl/end/").status_code, status)
        self.assertTrue(all(manager.get(user.pk) is None for user in self.users.values()))

    def test_a_disabled_repl_answers_404_to_everyone(self):
        client = client_for(self.users["owner"])
        with override_settings(ADMIN_EXTENSIONS={"REPL_ENABLED": False}):
            self.assertEqual(client.get("/admin/repl/state/").status_code, 404)
            self.assertEqual(post_json(client, "/admin/repl/start/").status_code, 404)
            self.assertEqual(
                async_to_sync(rejected)(ws_headers(self.users["owner"])), (False, 4404)
            )
        self.assertIsNone(manager.get(self.users["owner"].pk))

    def test_start_needs_post_with_csrf_and_page_render_starts_nothing(self):
        client = client_for(self.users["owner"], enforce_csrf_checks=True)
        page = client.get("/admin/testapp/device/")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'id="admin-ext-repl"', page.content)
        self.assertEqual(client.get("/admin/repl/start/").status_code, 405)
        self.assertEqual(post_json(client, "/admin/repl/start/").status_code, 403)
        self.assertIsNone(manager.get(self.users["owner"].pk))

    def test_start_and_end_check_csrf_even_without_the_middleware(self):
        from django.conf import settings

        middleware = [m for m in settings.MIDDLEWARE if "CsrfViewMiddleware" not in m]
        with override_settings(MIDDLEWARE=middleware):
            client = client_for(self.users["owner"], enforce_csrf_checks=True)
            self.assertEqual(post_json(client, "/admin/repl/start/").status_code, 403)
            self.assertEqual(post_json(client, "/admin/repl/end/").status_code, 403)
        self.assertIsNone(manager.get(self.users["owner"].pk))

    def test_staff_pages_render_without_the_tool(self):
        page = client_for(self.users["staff"]).get("/admin/")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"admin-ext-repl", page.content)

    def test_browser_picks_a_backend_name_never_a_command(self):
        client = client_for(self.users["owner"])
        self.assertEqual(
            post_json(client, "/admin/repl/start/", {"backend": "bash"}).status_code, 400
        )
        started = post_json(
            client,
            "/admin/repl/start/",
            {"backend": "python", "argv": ["sh", "-c", "id"], "command": "sh"},
        )
        self.assertEqual(started.status_code, 201)
        pid = started.json()["session"]["pid"]
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[1:-1]
        self.assertEqual(
            argv,
            [b"-m", b"django_extensions_admin.repl.pty_child", b"shell", b"--interface", b"python"],
        )

    def test_another_superuser_can_neither_see_nor_end_the_owners_session(self):
        owner = client_for(self.users["owner"])
        session_id = post_json(owner, "/admin/repl/start/", {"backend": "python"}).json()[
            "session"
        ]["id"]
        other = client_for(self.users["other"])
        self.assertIsNone(other.get("/admin/repl/state/").json()["session"])
        self.assertEqual(post_json(other, "/admin/repl/end/").status_code, 404)
        self.assertEqual(owner.get("/admin/repl/state/").json()["session"]["id"], session_id)
        self.assertIs(manager.get(self.users["owner"].pk).state, State.RUNNING)

    def test_websocket_refuses_anonymous_staff_inactive_nonstaff_and_foreign_origins(self):
        self.assertEqual(async_to_sync(rejected)(ws_headers()), (False, 4403))
        for name in ("staff", "inactive", "nonstaff"):
            with self.subTest(user=name):
                self.assertEqual(
                    async_to_sync(rejected)(ws_headers(self.users[name])), (False, 4403)
                )
        connected, _ = async_to_sync(rejected)(
            ws_headers(self.users["owner"], origin=b"http://evil.example")
        )
        self.assertFalse(connected)

    def test_owner_streams_resizes_and_runs_code_while_another_superuser_gets_nothing(self):
        owner_client = client_for(self.users["owner"])
        session_id = post_json(owner_client, "/admin/repl/start/", {"backend": "python"}).json()[
            "session"
        ]["id"]
        session = manager.get(self.users["owner"].pk)
        wait_output(session, ">>> ")
        owner_headers, other_headers = (
            ws_headers(self.users["owner"]),
            ws_headers(self.users["other"]),
        )

        async def scenario():
            other, connected, _ = await connect(other_headers)
            assert connected
            await other.send_to(
                text_data=json.dumps({"type": "attach", "session": session_id, "cursor": 0})
            )
            assert json.loads(await other.receive_from()) == {"type": "attached", "session": None}
            await other.send_to(text_data=json.dumps({"type": "resize", "cols": 33, "rows": 11}))
            await other.send_to(bytes_data=b"print('intruder')\r")

            owner, connected, _ = await connect(owner_headers)
            assert connected
            await owner.send_to(
                text_data=json.dumps({"type": "attach", "session": session_id, "cursor": 0})
            )
            attached = json.loads(await owner.receive_from())
            assert (attached["type"], attached["session"]["id"], attached["reset"]) == (
                "attached",
                session_id,
                False,
            )
            await owner.send_to(text_data=json.dumps({"type": "resize", "cols": 97, "rows": 29}))
            await owner.send_to(bytes_data=b"import os; print(7 * 191, os.get_terminal_size(0))\r")
            received, cursor, acks = b"", 0, []
            while (
                b"1337 os.terminal_size" not in received
                or b")\r\n" not in received.split(b"1337", 1)[1]
            ):
                frame = await owner.receive_output(timeout=10)
                if frame.get("bytes"):
                    offset = struct.unpack(">Q", frame["bytes"][:8])[0]
                    assert offset == cursor
                    cursor = offset + len(frame["bytes"]) - 8
                    received += frame["bytes"][8:]
                elif frame.get("text"):
                    message = json.loads(frame["text"])
                    if message["type"] == "resized":
                        acks.append((message["cols"], message["rows"]))
            await owner.disconnect()
            await other.disconnect()
            return received, acks

        received, acks = async_to_sync(scenario)()
        self.assertNotIn(b"intruder", received)
        self.assertIn(b"1337 os.terminal_size(columns=97, lines=29)", received)
        # The acknowledgement came before the output of the input sent after the resize.
        self.assertEqual(acks, [(97, 29)])
        self.assertIs(manager.get(self.users["owner"].pk).state, State.RUNNING)

    def test_deactivating_the_owner_revokes_the_stream_on_revalidation(self):
        from django_extensions_admin.repl import consumers

        owner_client = client_for(self.users["owner"])
        session_id = post_json(owner_client, "/admin/repl/start/", {"backend": "python"}).json()[
            "session"
        ]["id"]
        headers = ws_headers(self.users["owner"])
        previous = consumers.REVALIDATE_SECONDS
        consumers.REVALIDATE_SECONDS = 0.2
        self.addCleanup(setattr, consumers, "REVALIDATE_SECONDS", previous)

        async def scenario():
            communicator, connected, _ = await connect(headers)
            assert connected
            await communicator.send_to(
                text_data=json.dumps({"type": "attach", "session": session_id, "cursor": 0})
            )
            await communicator.receive_from()
            from channels.db import database_sync_to_async

            await database_sync_to_async(User.objects.filter(pk=self.users["owner"].pk).update)(
                is_active=False
            )
            while True:
                output = await communicator.receive_output(timeout=5)
                if output["type"] == "websocket.close":
                    return output["code"]

        self.assertEqual(async_to_sync(scenario)(), 4401)


class ChildEnvironmentTests(SimpleTestCase):
    def test_overridden_settings_still_name_the_servers_settings_module(self):
        from django_extensions_admin.repl.sessions import child_environment

        with repl_settings():
            self.assertEqual(child_environment()["DJANGO_SETTINGS_MODULE"], "tests.settings")

    def test_without_any_settings_module_starting_is_refused_cleanly(self):
        from unittest import mock

        from django_extensions_admin.repl.sessions import child_environment

        with repl_settings(), mock.patch.dict("os.environ", {"DJANGO_SETTINGS_MODULE": ""}):
            with self.assertRaisesRegex(ReplUnavailable, "settings module"):
                child_environment()
