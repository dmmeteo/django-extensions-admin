"""The command runner in a real browser, with a real, separately started db_worker.

The result page refreshes itself with a plain <meta> refresh, so the same journey works
with JavaScript switched off.
"""

from worker_tests.process import db_worker

from .base import ARTIFACTS, BrowserTestCase

INDEX = "/admin/commands/"
LAUNCH = "/admin/commands/demo_report/"
SETTINGS = "browser_tests.settings"
MARKUP = '<script>window.__pwned = 1</script><b id="bold">not bold</b>'


class CommandRunnerBrowserTests(BrowserTestCase):
    def worker(self):
        return db_worker(SETTINGS, ARTIFACTS.parent / "browser-db" / f"{self._testMethodName}.log")

    def launch(self, page, note=MARKUP, region="eu-west"):
        page.goto(f"{self.live_server_url}{LAUNCH}")
        page.select_option("#id_region", region)
        page.check("#id_list_devices")
        page.fill("#id_note", note)
        page.click('input[type="submit"][value="Run"]')
        page.wait_for_selector("[data-state]")
        return page

    def wait_for_success(self, page):
        # Up to ten automatic reloads; nothing clicks Refresh.
        page.wait_for_selector('[data-state="succeeded"]', timeout=30000)

    def test_launch_wait_for_a_worker_and_read_the_output_as_text(self):
        page = self.new_page()
        self.login(page)
        page.goto(f"{self.live_server_url}{INDEX}")
        page.wait_for_selector(f'a[href="{LAUNCH}"]')
        self.shot(page, "commands-index")
        page.goto(f"{self.live_server_url}{LAUNCH}")
        self.shot(page, "commands-form")

        self.launch(page)
        self.assertEqual(page.get_attribute("[data-state]", "data-state"), "queued")
        self.assertIn("Queued “Device report”.", page.inner_text(".messagelist"))
        self.shot(page, "commands-queued")

        with self.worker():
            self.wait_for_success(page)
        output = page.inner_text("#admin-ext-command-stdout")
        self.assertIn(f"Note: {MARKUP}", output)
        self.assertIn("eu-west:", output)
        self.assertIsNone(page.evaluate("() => window.__pwned"))
        self.assertEqual(page.locator("#admin-ext-command-stdout *").count(), 0)
        self.assertEqual(page.locator("#bold").count(), 0)
        self.shot(page, "commands-succeeded")

    def test_the_whole_journey_works_without_javascript(self):
        page = self.new_page(java_script_enabled=False)
        self.login(page)
        with self.worker():
            self.launch(page, note="no scripts here")
            self.wait_for_success(page)
        self.assertIn("Note: no scripts here", page.inner_text("#admin-ext-command-stdout"))
        self.shot(page, "commands-no-js")

    def test_dark_and_narrow_layouts_stay_usable(self):
        page = self.new_page(color_scheme="dark", viewport={"width": 375, "height": 812})
        self.login(page)
        page.goto(f"{self.live_server_url}{LAUNCH}")
        self.assertNoHorizontalScroll(page)
        self.shot(page, "commands-form-dark-narrow")
        with self.worker():
            self.launch(page, note="a-long-unbroken-token-" * 12)
            self.wait_for_success(page)
        self.assertNoHorizontalScroll(page)
        colours = page.evaluate(
            """() => {
                const pre = getComputedStyle(document.querySelector('.admin-ext-command-output'));
                const probe = document.createElement('div');
                probe.style.background = 'var(--darkened-bg)';
                probe.style.color = 'var(--body-fg)';
                document.body.appendChild(probe);
                const theme = getComputedStyle(probe);
                return [pre.backgroundColor, theme.backgroundColor, pre.color, theme.color];
            }"""
        )
        self.assertEqual(colours[0], colours[1], colours)  # the admin's own dark surface
        self.assertEqual(colours[2], colours[3], colours)
        self.shot(page, "commands-result-dark-narrow")

    def test_an_operator_without_the_permission_is_refused(self):
        page = self.new_page()
        self.login(page, "operator", "operator")
        page.goto(f"{self.live_server_url}{INDEX}")
        self.assertIn("no commands you have permission to run", page.inner_text("#content"))
        self.assertEqual(page.locator(f'a[href="{LAUNCH}"]').count(), 0)
        response = page.goto(f"{self.live_server_url}{LAUNCH}")
        self.assertEqual(response.status, 403)

    def assertNoHorizontalScroll(self, page):
        widths = page.evaluate(
            "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
        )
        self.assertLessEqual(widths[0], widths[1], widths)
