"""The shared tools panel, the REPL in it and the environment indicator, in Chromium.

These journeys run against a real daphne process on the live test database, because the
REPL streams over a WebSocket. Each test starts its own server, so a server's sessions and
the database flush between tests never meet.
"""

from django.contrib.auth.models import User

from .asgi_server import AsgiServer
from .base import ARTIFACTS, BrowserTestCase

REPL = "#admin-ext-repl"
PANEL = "#admin-ext-panel"
TOGGLE = "[data-admin-ext-panel-toggle]"

LAYOUT = """() => {
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height,
             top: r.top, bottom: r.bottom, left: r.left, right: r.right };
  };
  const panel = document.getElementById("admin-ext-panel");
  return {
    viewport: innerWidth,
    header: box(document.getElementById("header")),
    tools: box(document.getElementById("user-tools")),
    title: box(document.getElementById("site-name")),
    main: box(document.getElementById("main")),
    panel: panel && !panel.hidden ? box(panel) : null,
    overflow: document.documentElement.scrollWidth - innerWidth,
  };
}"""

GRID = """() => {
  const repl = document.getElementById("admin-ext-repl").adminExtRepl;
  const proposed = repl.proposed();
  const term = repl.terminal;
  const pty = repl.ptySize;
  return proposed && term && pty && term.cols === proposed.cols && term.rows === proposed.rows
    && pty.cols === term.cols && pty.rows === term.rows ? [term.cols, term.rows] : null;
}"""

SCREEN = """() => {
  const term = document.getElementById("admin-ext-repl").adminExtRepl.terminal;
  if (!term) return "";
  const buffer = term.buffer.active;
  const rows = [];
  for (let y = 0; y < buffer.length; y += 1) {
    rows.push(buffer.getLine(y)?.translateToString(true) ?? "");
  }
  return rows.join("\\n");
}"""


class PanelJourney(BrowserTestCase):
    """Helpers shared by the journeys: a daphne server, the panel, the terminal."""

    server_env = {"BROWSER_REPL": "1"}

    def setUp(self):
        super().setUp()
        self.server = AsgiServer(
            ARTIFACTS.parent / "daphne" / f"{self._testMethodName}.log", self.server_env
        )
        self.server.start()
        self.addCleanup(self.server.stop)
        self.url = self.server.url
        # A browser that turns a WebAssembly trap into an exception, not a renderer crash, would
        # otherwise let a failed terminal write pass silently until a screen wait times out.
        self.page_errors = []
        self.addCleanup(lambda: self.assertEqual(self.page_errors, [], "uncaught page errors"))

    def open_page(self, path="/admin/", username="demo", **context):
        page = self.new_page(**context)
        page.on("pageerror", lambda e: self.page_errors.append(f"{e.name}: {e.message}"))
        page.goto(f"{self.url}/admin/login/?next={path}")
        page.fill("#id_username", username)
        page.fill("#id_password", username)
        page.click('input[type="submit"]')
        page.wait_for_selector("#user-tools")
        return page

    def layout(self, page):
        return page.evaluate(LAYOUT)

    def open_panel(self, page):
        page.get_by_role("button", name="Tools panel").click()
        page.wait_for_selector(f"{PANEL}:not([hidden])")
        page.wait_for_function(
            "() => document.querySelector('#admin-ext-repl [data-role=launch]')?.hidden === false"
            " || document.querySelector('#admin-ext-repl [data-role=state]')?.textContent"
            " === 'Live'"
        )

    def wait_state(self, page, label, timeout=30000):
        page.wait_for_function(
            "(label) => document.querySelector('#admin-ext-repl [data-role=state]')?"
            ".textContent === label",
            arg=label,
            timeout=timeout,
        )

    def screen(self, page):
        return page.evaluate(SCREEN)

    def wait_screen(self, page, needle, timeout=60000):
        try:
            page.wait_for_function(
                f"(needle) => ({SCREEN})().includes(needle)",
                arg=needle,
                timeout=timeout,
                polling=100,
            )
        except Exception as error:
            raise AssertionError(
                f"terminal never showed {needle!r}; screen:\n{self.screen(page)[-1500:]}"
            ) from error

    def start(self, page, backend=None, prompt="In ["):
        if backend:
            page.select_option(f"{REPL} [data-role=backend]", backend)
        page.click(f"{REPL} [data-action=start]")
        self.wait_state(page, "Live")
        self.wait_screen(page, prompt)
        return page.evaluate("() => document.getElementById('admin-ext-repl').adminExtRepl.session")

    def type_code(self, page, code, expected=None):
        page.locator(f"{REPL} [data-role=screen] canvas").click()
        page.keyboard.type(code)
        page.keyboard.press("Enter")
        if expected:
            self.wait_screen(page, expected)

    def settled_grid(self, page):
        """The grid once Ghostty fits the screen and the server confirmed the PTY has that size."""
        # The value the wait saw, not a second read: a redraw 250 ms after a resize re-attaches and
        # forgets the acknowledged size until the server confirms it again.
        return page.wait_for_function(GRID, timeout=15000).json_value()

    def assert_pty_grid(self, page, tag):
        cols, rows = self.settled_grid(page)
        self.type_code(
            page,
            f'import os; print("{tag}", *os.get_terminal_size(0), marker)',
            f"{tag} {cols} {rows} 42",
        )
        return cols

    def drag(self, page, dx):
        handle = page.locator(f"{PANEL} [data-panel-role=resize]")
        box = handle.bounding_box()
        x, y = round(box["x"] + box["width"] / 2), round(box["y"] + box["height"] / 3)
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + dx // 2, y, steps=6)
        page.mouse.move(x + dx, y, steps=6)
        page.mouse.up()

    def touch_drag(self, page, dx):
        """A real touchscreen drag on the separator (CDP touch events, not synthetic DOM ones)."""
        box = page.locator(f"{PANEL} [data-panel-role=resize]").bounding_box()
        x, y = round(box["x"] + box["width"] / 2), round(box["y"] + box["height"] / 3)
        cdp = page.context.new_cdp_session(page)
        cdp.send(
            "Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [{"x": x, "y": y}]}
        )
        for step in range(1, 7):
            point = {"x": x + dx * step / 6, "y": y}
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [point]})
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    def width(self, page):
        return round(self.layout(page)["panel"]["width"])

    def assert_overlay_on_a_narrow_screen(self, page, closed, side, label):
        """Below 760 px the panel overlays the page below the header, inside the viewport."""
        layout = self.layout(page)
        panel, viewport = layout["panel"], layout["viewport"]
        self.assert_header_kept(closed, layout, label)
        self.assertGreaterEqual(panel["top"], layout["header"]["bottom"] - 0.5, label)
        self.assertGreaterEqual(panel["left"], 0, f"{label}: panel starts on screen")
        self.assertLessEqual(panel["right"], viewport + 0.5, f"{label}: panel ends on screen")
        self.assertLessEqual(layout["overflow"], 0, f"{label}: nothing scrolls sideways")
        handle = page.locator(f"{PANEL} [data-panel-role=resize]")
        self.assertTrue(handle.is_visible(), f"{label}: the resize handle is visible")
        box = handle.bounding_box()
        self.assertGreaterEqual(box["x"], 0, f"{label}: handle on screen")
        self.assertLessEqual(box["x"] + box["width"], viewport, f"{label}: handle on screen")
        close = page.locator(f"{PANEL} [data-panel-action=close]").bounding_box()
        self.assertGreaterEqual(close["x"], panel["left"], f"{label}: Close inside the panel")
        self.assertLessEqual(close["x"] + close["width"], viewport, f"{label}: Close on screen")
        return panel["width"]

    def assert_header_kept(self, closed, now, label):
        for key in ("x", "y", "width", "height"):
            self.assertAlmostEqual(
                now["header"][key], closed["header"][key], delta=0.5, msg=f"{label}: header {key}"
            )
            self.assertAlmostEqual(
                now["tools"][key], closed["tools"][key], delta=0.5, msg=f"{label}: user tools {key}"
            )
        self.assertAlmostEqual(
            now["title"]["height"],
            closed["title"]["height"],
            delta=0.5,
            msg=f"{label}: title wraps",
        )
        self.assertAlmostEqual(
            now["header"]["width"],
            now["viewport"],
            delta=0.5,
            msg=f"{label}: header spans the viewport",
        )

    def assert_docked_below_header(self, layout, side, label):
        panel, header, main = layout["panel"], layout["header"], layout["main"]
        self.assertIsNotNone(panel, f"{label}: panel visible")
        self.assertGreaterEqual(
            panel["top"], header["bottom"] - 0.5, f"{label}: panel starts below the header"
        )
        self.assertLessEqual(
            panel["top"], header["bottom"] + 1, f"{label}: panel starts at the header's edge"
        )
        if side == "right":
            self.assertLessEqual(
                main["right"], panel["left"] + 0.5, f"{label}: content ends where the panel starts"
            )
        else:
            self.assertGreaterEqual(
                main["left"], panel["right"] - 0.5, f"{label}: content starts where the panel ends"
            )
        self.assertAlmostEqual(
            main["width"],
            layout["viewport"] - panel["width"],
            delta=1,
            msg=f"{label}: content width",
        )
        self.assertLessEqual(layout["overflow"], 0, f"{label}: nothing scrolls sideways")


class RightPanelTests(PanelJourney):
    def test_the_panel_docks_below_the_full_width_header_and_resizes_only_the_content(self):
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                page = self.open_page(
                    "/admin/demoapp/device/",
                    color_scheme=theme,
                    viewport={"width": 1440, "height": 900},
                )
                closed = self.layout(page)
                self.assertIsNone(closed["panel"])
                button = page.get_by_role("button", name="Tools panel")
                self.assertEqual(button.get_attribute("title"), "Tools panel (Ctrl+`)")
                self.assertEqual(button.inner_text().strip(), "")
                self.open_panel(page)
                opened = self.layout(page)
                self.assert_header_kept(closed, opened, f"{theme} open")
                self.assert_docked_below_header(opened, "right", f"{theme} open")
                self.assertEqual(button.get_attribute("aria-expanded"), "true")
                self.shot(page, f"panel-right-{theme}-1440")

                self.drag(page, -200)
                dragged = self.layout(page)
                self.assertAlmostEqual(
                    dragged["panel"]["width"], opened["panel"]["width"] + 200, delta=1
                )
                self.assert_header_kept(closed, dragged, f"{theme} dragged")
                self.assert_docked_below_header(dragged, "right", f"{theme} dragged")

                handle = page.locator(f"{PANEL} [data-panel-role=resize]")
                handle.focus()
                page.keyboard.press("End")
                widest = self.layout(page)
                self.assertAlmostEqual(
                    widest["panel"]["width"],
                    1440 - 400,
                    delta=1,
                    msg="End clamps to the page minimum",
                )
                self.assert_header_kept(closed, widest, f"{theme} widest")
                page.keyboard.press("Home")
                self.assertAlmostEqual(
                    self.layout(page)["panel"]["width"], 360, delta=1, msg="Home clamps to 360 px"
                )
                page.keyboard.press("Shift+ArrowLeft")
                self.assertAlmostEqual(self.layout(page)["panel"]["width"], 440, delta=1)
                self.assertEqual(handle.get_attribute("aria-valuenow"), "440")
                self.drag(page, -3000)
                self.assertAlmostEqual(
                    self.layout(page)["panel"]["width"], 1040, delta=1, msg="drag clamps"
                )

                page.reload()
                page.wait_for_selector(f"{PANEL}:not([hidden])")
                reloaded = self.layout(page)
                self.assertAlmostEqual(
                    reloaded["panel"]["width"], 1040, delta=1, msg="width survives reload"
                )
                self.assert_header_kept(closed, reloaded, f"{theme} reloaded")
                page.get_by_role("link", name="Readings").first.click()
                page.wait_for_selector(f"{PANEL}:not([hidden])")
                navigated = self.layout(page)
                self.assert_docked_below_header(navigated, "right", f"{theme} navigated")
                self.assertEqual(
                    page.evaluate(
                        "() => document.getElementById('header').getBoundingClientRect().width"
                    ),
                    1440,
                )
                page.get_by_role("button", name="Close").click()
                self.assertEqual(
                    page.evaluate("document.activeElement.dataset.adminExtPanelToggle"), ""
                )
                self.assertIsNone(self.layout(page)["panel"])
                page.context.close()

    def test_scrolling_moves_the_header_away_and_the_panel_follows_to_the_top(self):
        page = self.open_page("/admin/demoapp/reading/", viewport={"width": 1280, "height": 600})
        self.open_panel(page)
        start = self.layout(page)
        self.assert_docked_below_header(start, "right", "top of page")
        page.mouse.wheel(0, 400)
        page.wait_for_function("() => window.scrollY > 0")
        scrolled = self.layout(page)
        self.assertLess(
            scrolled["header"]["bottom"],
            start["header"]["bottom"],
            "the header scrolls with the page",
        )
        self.assertAlmostEqual(
            scrolled["panel"]["top"], max(0, scrolled["header"]["bottom"]), delta=1
        )

    def test_a_phone_resizes_the_panel_by_touch_drag_and_keys_and_the_grid_follows(self):
        page = self.open_page(
            "/admin/demoapp/device/", viewport={"width": 375, "height": 812}, has_touch=True
        )
        closed = self.layout(page)
        self.open_panel(page)
        widest = self.assert_overlay_on_a_narrow_screen(page, closed, "right", "375 open")
        self.assertAlmostEqual(
            widest, 375 - 32, delta=1, msg="opens at its widest, a strip of page left"
        )
        session = self.start(page)
        self.type_code(page, "marker = 42", None)
        self.assert_pty_grid(page, "grid-375-open")

        self.touch_drag(page, 100)
        self.assertAlmostEqual(self.width(page), widest - 100, delta=2, msg="touch drag narrows it")
        self.assert_overlay_on_a_narrow_screen(page, closed, "right", "375 touch-dragged")
        narrowed = self.assert_pty_grid(page, "grid-375-touch")
        self.drag(page, -60)
        self.assertAlmostEqual(self.width(page), widest - 40, delta=2, msg="pointer drag widens it")
        handle = page.locator(f"{PANEL} [data-panel-role=resize]")
        handle.focus()
        page.keyboard.press("Home")
        self.assertEqual(self.width(page), 240, "Home: the narrow minimum")
        self.assertEqual(handle.get_attribute("aria-valuemin"), "240")
        page.keyboard.press("Shift+ArrowLeft")
        self.assertEqual(self.width(page), 320)
        page.keyboard.press("End")
        self.assertEqual(self.width(page), 375 - 32, "End: the narrow maximum")
        page.keyboard.press("Shift+ArrowRight")
        self.assertEqual(self.width(page), 375 - 32 - 80)
        self.assert_overlay_on_a_narrow_screen(page, closed, "right", "375 keys")
        keyed = self.assert_pty_grid(page, "grid-375-keys")
        self.assertNotEqual(keyed, narrowed)
        self.shot(page, "panel-right-375")

        page.reload()
        self.wait_state(page, "Live")
        self.assertEqual(self.width(page), 375 - 32 - 80, "width survives reload")
        self.type_code(page, 'print("after-reload", marker)', "after-reload 42")
        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_function("() => innerWidth === 1280")
        desktop = self.layout(page)
        self.assertEqual(
            round(desktop["panel"]["width"]), 360, "a phone width clamps up to 360 docked"
        )
        self.assert_docked_below_header(desktop, "right", "back on a desktop")
        self.assert_pty_grid(page, "grid-1280")
        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_function("() => innerWidth === 375")
        self.assertEqual(self.width(page), 375 - 32 - 80, "the stored width comes back")
        self.assert_pty_grid(page, "grid-375-again")
        self.assertEqual(
            page.evaluate(
                "() => document.getElementById('admin-ext-repl').adminExtRepl.session.pid"
            ),
            session["pid"],
        )

    def test_shell_keeps_its_process_across_navigation_reload_and_resizing(self):
        page = self.open_page("/admin/", viewport={"width": 1440, "height": 900})
        self.assertEqual(page.locator(f"{PANEL}").count(), 1)
        self.open_panel(page)
        launch = page.locator(f"{REPL} [data-role=backend] option").all_inner_texts()
        self.assertIn("Django shell (Python)", launch)
        session = self.start(page)
        self.type_code(page, "marker = 6 * 7", None)
        self.type_code(page, 'print(f"value={marker * 1000}")', "value=42000")
        cols = self.assert_pty_grid(page, "grid-open")

        page.get_by_role("link", name="Devices").first.click()
        self.wait_state(page, "Live")
        self.assertEqual(
            page.evaluate(
                "() => document.getElementById('admin-ext-repl').adminExtRepl.session.pid"
            ),
            session["pid"],
        )
        self.type_code(page, 'print("after-nav", marker)', "after-nav 42")
        page.reload()
        self.wait_state(page, "Live")
        self.wait_screen(page, "after-nav 42")
        self.assertEqual(self.screen(page).count("value=42000"), 1, "history replays once")
        self.type_code(page, 'print("after-reload", marker)', "after-reload 42")

        self.drag(page, -240)
        wide = self.assert_pty_grid(page, "grid-drag")
        self.assertGreater(wide, cols)
        page.locator(f"{PANEL} [data-panel-role=resize]").focus()
        page.keyboard.press("Shift+ArrowRight")
        narrower = self.assert_pty_grid(page, "grid-key")
        self.assertLess(narrower, wide)
        page.get_by_role("button", name="Full width").click()
        full = self.assert_pty_grid(page, "grid-full")
        self.assertGreater(full, wide)
        layout = self.layout(page)
        self.assertAlmostEqual(layout["panel"]["width"], 1440, delta=1)
        self.assertGreaterEqual(layout["panel"]["top"], layout["header"]["bottom"] - 0.5)
        page.get_by_role("button", name="Docked width").click()
        self.assert_pty_grid(page, "grid-docked")
        self.shot(page, "repl-right-live")

        page.keyboard.press("Control+`")
        page.wait_for_selector(f"{PANEL}[hidden]", state="attached")
        page.keyboard.press("Control+`")
        self.wait_state(page, "Live")
        self.type_code(page, 'print("reopened", marker)', "reopened 42")

        page.once("dialog", lambda dialog: dialog.accept())
        page.click(f"{REPL} [data-action=end]")
        self.wait_state(page, "Ended")

    def test_a_width_change_in_the_frame_after_a_refit_still_reaches_the_grid(self):
        page = self.open_page("/admin/", viewport={"width": 1440, "height": 900})
        self.open_panel(page)
        self.start(page)
        self.type_code(page, "marker = 42", None)
        self.settled_grid(page)
        # The second width change comes from inside the terminal's own resize event, so the next
        # refit attempt lands in the next frame: inside the 50 ms in which ghostty-web 0.4.0's
        # FitAddon.fit() ignores calls, and long before the 250 ms redraw.
        result = page.evaluate("""async () => {
          const frame = () => new Promise((resolve) => requestAnimationFrame(resolve));
          const handle = document.querySelector("#admin-ext-panel [data-panel-role=resize]");
          const press = (key) => handle.dispatchEvent(
            new KeyboardEvent("keydown", { key, shiftKey: true, bubbles: true }));
          const repl = document.getElementById("admin-ext-repl").adminExtRepl;
          const term = repl.terminal;
          const first = await new Promise((resolve, reject) => {
            const subscription = term.onResize(({ cols }) => {
              subscription.dispose();
              press("ArrowLeft");
              resolve({ cols, at: performance.now() });
            });
            press("ArrowLeft");
            setTimeout(() => reject(new Error("the first change never resized the grid")), 5000);
          });
          const next = await frame();
          await frame(); await frame(); await frame();
          const proposed = repl.proposed().cols;
          return { first: first.cols, gap: next - first.at, cols: term.cols, proposed };
        }""")
        # These hold whatever the timing: the grid follows both changes.
        self.assertGreater(result["proposed"], result["first"], result)
        self.assertEqual(result["cols"], result["proposed"], result)
        self.assert_pty_grid(page, "grid-refit")
        # Only a refit attempt inside the 50 ms window tells the fix from FitAddon.fit(); a
        # slower frame cannot, and says so instead of counting as proof.
        if result["gap"] >= 50:
            self.skipTest(
                f"inconclusive as a regression check: next frame {result['gap']:.0f} ms on"
            )

    def test_a_terminal_replacement_that_loads_late_never_takes_a_newer_screen(self):
        page = self.open_page("/admin/", viewport={"width": 1440, "height": 900})
        self.open_panel(page)
        self.start(page)
        self.type_code(page, 'print("first-" + "session")', "first-session")
        self.settled_grid(page)
        # A redraw loads a new WebAssembly instance for its terminal. Once the test arms `hold`, the
        # next load is kept waiting until the test releases it; every other load goes through.
        hold, held = [], []

        def route_wasm(route):
            if hold:
                hold.pop()
                held.append(route)
            else:
                route.continue_()

        page.route("**/ghostty-vt.wasm", route_wasm)
        page.evaluate("""() => {
          window.wasmInstances = 0;
          const instantiate = WebAssembly.instantiate;
          WebAssembly.instantiate = (...args) =>
            instantiate(...args).then((result) => { window.wasmInstances += 1; return result; });
        }""")
        handle = page.locator(f"{PANEL} [data-panel-role=resize]")
        loaded = "() => window.wasmInstances"

        def redraw_and_hold():
            hold.append(True)
            handle.focus()
            page.keyboard.press("Shift+ArrowLeft")
            for _ in range(100):
                if held:
                    return
                page.wait_for_timeout(100)
            self.fail("the resize never started a redraw")

        def redraw():
            before = page.evaluate(loaded)
            handle.focus()
            page.keyboard.press("Shift+ArrowLeft")
            page.wait_for_function(f"(n) => ({loaded})() > n", arg=before)

        def release_and_wait():
            before = page.evaluate(loaded)
            held.pop().continue_()
            page.wait_for_function(f"(n) => ({loaded})() > n", arg=before)

        # While the redraw waits: End, a new session, its output and another redraw.
        redraw_and_hold()
        page.once("dialog", lambda dialog: dialog.accept())
        page.click(f"{REPL} [data-action=end]")
        self.wait_state(page, "Ended")
        self.start(page)
        self.type_code(page, 'print("second-" + "session")', "second-session")
        redraw()
        self.settled_grid(page)
        self.wait_screen(page, "second-session")
        release_and_wait()
        self.type_code(page, 'print("after-" + "late")', "after-late")
        screen = self.screen(page)
        self.assertEqual(screen.count("second-session"), 1, screen[-1500:])
        self.assertNotIn("first-session", screen)

        # A redraw that finishes after End leaves the ended session's screen, and stays ended.
        redraw_and_hold()
        page.once("dialog", lambda dialog: dialog.accept())
        page.click(f"{REPL} [data-action=end]")
        self.wait_state(page, "Ended")
        release_and_wait()
        self.wait_state(page, "Ended")
        self.assertIn("after-late", self.screen(page))
        self.assertTrue(page.locator(f"{REPL} [data-action=start]").is_visible())

    def test_ordinary_admin_forms_still_work_beside_the_open_panel(self):
        page = self.open_page("/admin/demoapp/device/add/", viewport={"width": 1280, "height": 900})
        self.open_panel(page)
        page.fill("#id_name", "beside-panel")
        page.locator('input[name="_save"]').click()
        page.wait_for_selector(".messagelist .success")
        self.assertIn("beside-panel", page.locator(".messagelist").inner_text())
        self.assert_docked_below_header(self.layout(page), "right", "after save")

    def test_staff_without_superuser_and_anonymous_get_nothing(self):
        page = self.open_page("/admin/", username="operator")
        self.assertEqual(page.locator(TOGGLE).count(), 0)
        self.assertEqual(page.locator(PANEL).count(), 0)
        self.assertEqual(page.request.get(f"{self.url}/admin/repl/state/").status, 403)
        anonymous = self.new_page()
        self.assertEqual(anonymous.request.get(f"{self.url}/admin/repl/state/").status, 401)

    def test_a_server_restart_ends_the_process_and_says_so_then_builtin_python_starts_cold(self):
        page = self.open_page("/admin/", viewport={"width": 1280, "height": 900})
        self.open_panel(page)
        old = self.start(page)
        self.type_code(page, "marker = 42", None)
        self.server.restart()
        page.reload()
        page.wait_for_selector(f"{PANEL}:not([hidden])")
        page.wait_for_function(
            "() => document.querySelector('#admin-ext-repl [data-role=notice]')?"
            ".textContent.includes('no longer exists')"
        )
        self.assertIn(old["id"][:8], page.locator(f"{REPL} [data-role=notice]").inner_text())
        self.wait_state(page, "Not started")
        session = self.start(page, "python", ">>>")
        self.assertNotEqual(session["pid"], old["pid"])
        self.type_code(page, "print(sum(range(10)) * 7)", "315")
        self.type_code(page, "marker = 42", None)
        self.assert_pty_grid(page, "grid-cold")


class LeftPanelTests(PanelJourney):
    server_env = {"BROWSER_REPL": "1", "BROWSER_PANEL_SIDE": "left"}

    def test_left_side_docks_below_the_header_and_its_drag_and_keys_mirror(self):
        page = self.open_page("/admin/demoapp/device/", viewport={"width": 1440, "height": 900})
        closed = self.layout(page)
        self.open_panel(page)
        opened = self.layout(page)
        self.assertAlmostEqual(opened["panel"]["left"], 0, delta=0.5)
        self.assert_header_kept(closed, opened, "left open")
        self.assert_docked_below_header(opened, "left", "left open")
        self.drag(page, 200)
        dragged = self.layout(page)
        self.assertAlmostEqual(dragged["panel"]["width"], opened["panel"]["width"] + 200, delta=1)
        self.assert_header_kept(closed, dragged, "left dragged")
        self.assert_docked_below_header(dragged, "left", "left dragged")
        page.locator(f"{PANEL} [data-panel-role=resize]").focus()
        page.keyboard.press("Shift+ArrowRight")
        self.assertAlmostEqual(
            self.layout(page)["panel"]["width"], dragged["panel"]["width"] + 80, delta=1
        )
        page.keyboard.press("Shift+ArrowLeft")
        page.keyboard.press("Shift+ArrowLeft")
        self.assertAlmostEqual(
            self.layout(page)["panel"]["width"], dragged["panel"]["width"] - 80, delta=1
        )
        self.start(page)
        self.type_code(page, "marker = 42", None)
        self.assert_pty_grid(page, "grid-left")
        self.drag(page, 240)
        self.assert_pty_grid(page, "grid-left-wide")
        self.assert_header_kept(closed, self.layout(page), "left live")
        self.shot(page, "repl-left-live")
        page.context.close()

        narrow = self.open_page("/admin/", viewport={"width": 390, "height": 844})
        closed_narrow = self.layout(narrow)
        self.open_panel(narrow)
        widest = self.assert_overlay_on_a_narrow_screen(narrow, closed_narrow, "left", "left 390")
        self.assertAlmostEqual(self.layout(narrow)["panel"]["left"], 0, delta=0.5)
        self.wait_state(narrow, "Live")
        self.type_code(narrow, 'print("left-narrow", marker)', "left-narrow 42")
        self.drag(narrow, -90)
        self.assertAlmostEqual(
            self.width(narrow), widest - 90, delta=2, msg="inward drag narrows it"
        )
        self.assert_overlay_on_a_narrow_screen(narrow, closed_narrow, "left", "left 390 dragged")
        dragged = self.assert_pty_grid(narrow, "grid-left-390-drag")
        narrow.locator(f"{PANEL} [data-panel-role=resize]").focus()
        narrow.keyboard.press("Shift+ArrowRight")
        self.assertAlmostEqual(self.width(narrow), widest - 10, delta=2, msg="ArrowRight widens it")
        self.assertNotEqual(self.assert_pty_grid(narrow, "grid-left-390-key"), dragged)
        self.shot(narrow, "repl-left-390")


class EnvironmentTests(PanelJourney):
    server_env = {"BROWSER_REPL": "1", "BROWSER_ENVIRONMENT": "Staging"}

    def test_the_indicator_is_a_line_and_a_readable_badge_above_the_unchanged_header(self):
        page = self.open_page("/admin/", viewport={"width": 1280, "height": 800})
        indicator = page.evaluate("""() => {
          const line = document.querySelector(".admin-ext-environment").getBoundingClientRect();
          const badge = document.querySelector(".admin-ext-environment-name");
          const b = badge.getBoundingClientRect();
          const style = getComputedStyle(badge);
          return { line: [line.top, line.height, line.width], badge: [b.top, b.height, b.width],
                   text: badge.textContent, font: parseFloat(style.fontSize), color: style.color,
                   background: style.backgroundColor,
                   header: document.getElementById("header").getBoundingClientRect().top };
        }""")
        self.assertEqual(indicator["line"], [0, 5, 1280])
        self.assertEqual(indicator["header"], 5)
        self.assertEqual(indicator["text"], "Staging")
        self.assertGreaterEqual(indicator["font"], 11)
        self.assertGreaterEqual(indicator["badge"][1], 14)
        self.assertEqual(indicator["background"], "rgb(186, 33, 33)")
        self.assertEqual(indicator["color"], "rgb(255, 255, 255)")
        self.open_panel(page)
        layout = self.layout(page)
        self.assert_docked_below_header(layout, "right", "with indicator")
        line = page.locator(".admin-ext-environment").evaluate(
            "el => el.getBoundingClientRect().width"
        )
        self.assertEqual(
            line, 1280, "the indicator's line keeps the full width with the panel open"
        )
        self.shot(page, "environment-top-panel")
        login = self.new_page(viewport={"width": 1280, "height": 800})
        login.goto(f"{self.url}/admin/login/")
        self.assertEqual(login.locator(".admin-ext-environment-name").inner_text(), "STAGING")
        self.shot(login, "environment-login")


class BottomEnvironmentTests(PanelJourney):
    server_env = {"BROWSER_REPL": "1", "BROWSER_ENVIRONMENT": "QA bottom"}

    def setUp(self):
        self.server_env = {**self.server_env, "BROWSER_ENVIRONMENT_POSITION": "bottom"}
        super().setUp()

    def test_bottom_position_keeps_the_header_first_and_the_panel_above_the_line(self):
        page = self.open_page("/admin/", viewport={"width": 1280, "height": 800})
        line = page.locator(".admin-ext-environment").evaluate(
            "el => el.getBoundingClientRect().toJSON()"
        )
        self.assertEqual((line["bottom"], line["height"]), (800, 5))
        self.assertEqual(
            page.evaluate("() => document.getElementById('header').getBoundingClientRect().top"), 0
        )
        self.open_panel(page)
        panel = self.layout(page)["panel"]
        self.assertLessEqual(panel["bottom"], 795.5)
        self.shot(page, "environment-bottom-panel")


class NoToolTests(BrowserTestCase):
    def test_without_an_enabled_tool_the_stock_header_has_no_panel_button(self):
        page = self.login(self.new_page())
        self.assertEqual(page.locator(TOGGLE).count(), 0)
        self.assertEqual(page.locator(".admin-ext-environment").count(), 0)
        self.assertTrue(User.objects.filter(username="demo", is_superuser=True).exists())
