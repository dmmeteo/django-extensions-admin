"""Shared Playwright plumbing for the browser smoke tests."""

import os
import pathlib

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command

ARTIFACTS = pathlib.Path(
    os.environ.get("ADMIN_EXTENSIONS_ARTIFACTS")
    or pathlib.Path(__file__).resolve().parent.parent / "artifacts" / "browser"
)


class BrowserTestCase(StaticLiveServerTestCase):
    """One browser for the whole class; a fresh page per test."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from playwright.sync_api import sync_playwright

        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        call_command("seed_demo", verbosity=0)

    def new_page(self, **context_kwargs):
        context = self.browser.new_context(**context_kwargs)
        self.addCleanup(context.close)
        page = context.new_page()
        page.set_default_timeout(15000)
        return page

    def login(self, page, username="demo", password="demo"):
        page.goto(f"{self.live_server_url}/admin/login/")
        page.fill("#id_username", username)
        page.fill("#id_password", password)
        page.click('input[type="submit"]')
        page.wait_for_selector("#user-tools")
        return page

    def shot(self, page, name):
        path = ARTIFACTS / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        return path

    def reading_change_url(self, label):
        from demoapp.models import Reading

        reading = Reading.objects.get(label=label)
        return f"{self.live_server_url}/admin/demoapp/reading/{reading.pk}/change/"
