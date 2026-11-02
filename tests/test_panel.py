"""The shared tools panel renders only for a request some tool is available to."""

import re

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from django_extensions_admin.panel.checks import check_panel

ENABLED = {"REPL_ENABLED": True}


def toggle(page):
    match = re.search(r"<button[^>]*data-admin-ext-panel-toggle[^>]*>.*?</button>", page, re.S)
    return match.group(0) if match else None


class PanelRenderingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("root", "root@example.invalid", "pw")
        cls.staff = User.objects.create_user("staff", is_staff=True, password="pw")

    def page(self, user, url="/admin/"):
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_installed_but_not_enabled_renders_nothing(self):
        page = self.page(self.root)
        self.assertNotIn("admin-ext-panel", page)
        self.assertNotIn("admin-ext-repl", page)

    @override_settings(ADMIN_EXTENSIONS=ENABLED)
    def test_staff_without_superuser_gets_no_panel_even_when_enabled(self):
        self.assertNotIn("admin-ext-panel", self.page(self.staff))

    @override_settings(ADMIN_EXTENSIONS=ENABLED)
    def test_an_enabled_tool_adds_one_icon_button_beside_the_theme_toggle(self):
        page = self.page(self.root)
        button = toggle(page)
        self.assertIsNotNone(button)
        self.assertIn('aria-label="Tools panel"', button)
        self.assertIn('aria-expanded="false"', button)
        self.assertIn('aria-controls="admin-ext-panel"', button)
        self.assertIn('title="Tools panel (Ctrl+`)"', button)
        # No visible text: the accessible name is the label, the face is an icon.
        self.assertEqual(re.sub(r"<[^>]+>", "", button).strip(), "")
        self.assertNotIn("REPL", button)
        user_tools = page[page.index('<div id="user-tools">') : page.index("</header>")]
        self.assertLess(
            user_tools.index('class="theme-toggle"'),
            user_tools.index("data-admin-ext-panel-toggle"),
        )

    @override_settings(ADMIN_EXTENSIONS=ENABLED)
    def test_the_panel_lists_the_available_tools_as_tabs_and_starts_hidden(self):
        page = self.page(self.root)
        self.assertIn(
            '<aside id="admin-ext-panel" class="admin-ext-panel" data-side="right"'
            ' aria-label="Tools" hidden>',
            page,
        )
        self.assertEqual(re.findall(r'role="tab" id="admin-ext-panel-tab-(\w+)"', page), ["repl"])
        self.assertIn('id="admin-ext-repl"', page)
        # Rendering a page starts nothing: the panel only describes where the tool lives.
        from django_extensions_admin.repl.sessions import manager

        self.assertIsNone(manager.get(self.root.pk))

    @override_settings(ADMIN_EXTENSIONS={**ENABLED, "PANEL_SIDE": "left"})
    def test_left_side_reaches_the_boot_script_the_panel_and_the_icon(self):
        page = self.page(self.root)
        self.assertIn('panel/boot.js" data-side="left"', page)
        self.assertIn('data-side="left" aria-label="Tools" hidden>', page)
        self.assertIn('class="admin-ext-panel-icon" data-side="left"', page)

    @override_settings(ADMIN_EXTENSIONS=ENABLED)
    def test_popups_never_get_the_panel(self):
        self.assertNotIn("admin-ext-panel", self.page(self.root, "/admin/auth/user/add/?_popup=1"))

    @override_settings(ADMIN_EXTENSIONS=ENABLED)
    def test_login_page_gets_no_panel(self):
        self.client.logout()
        response = self.client.get("/admin/login/")
        self.assertNotIn("admin-ext-panel", response.content.decode())

    def test_side_is_validated(self):
        for value, ids in (("right", []), ("left", []), ("top", ["django_extensions_admin.E401"])):
            with (
                self.subTest(value=value),
                override_settings(ADMIN_EXTENSIONS={"PANEL_SIDE": value}),
            ):
                self.assertEqual([m.id for m in check_panel()], ids)
