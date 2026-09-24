"""Branding: explicit adoption, additive markup, validated values, the stock admin intact.

A project adopts branding with its own ``admin/base_site.html`` extending the package's
template; ``tests/branding_templates`` is that project template. Without it, the setting
changes nothing at all.
"""

import copy
import re
from importlib.util import find_spec
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings

from django_extensions_admin.branding import DARK_SENSITIVE, PALETTE, check_branding

from .testapp.admin import restricted_site
from .testapp.models import Device, Reading

HERE = Path(__file__).resolve().parent
LOGO = "testapp/brand-logo.svg"
BRANDING = {
    "LOGO": LOGO,
    "COLORS": {"secondary": "#1f3a5f", "accent": "#f2c14e", "primary": "#5b7fa6"},
    "DARK_COLORS": {"primary": "#23384f"},
}


def templates(*dirs):
    engines = copy.deepcopy(settings.TEMPLATES)
    engines[0]["DIRS"] = [str(HERE / d) for d in dirs]
    return engines


def branding(value=BRANDING, adopt="branding_templates"):
    """Settings for a project that configured branding, and adopted it unless adopt=None."""
    values = {"COMMANDS_TASK_BACKEND": "commands", "BRANDING": value}
    return override_settings(
        ADMIN_EXTENSIONS=values, TEMPLATES=templates(*([adopt] if adopt else []))
    )


def normalized(html):
    """The page without what legitimately differs between two renders: CSRF tokens."""
    return re.sub(r'(name="csrfmiddlewaretoken" value=")[^"]+', r"\1-", html)


def main(html):
    match = re.search(r'<main id="content-start".*?</main>', html, re.S)
    assert match, "no <main> in the page"
    return normalized(match.group(0))


def style(html):
    match = re.search(r"<style[^>]*>(.*?)</style>", html, re.S)
    return match.group(1) if match else None


class BrandingCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("root", "root@example.invalid", "pw")
        cls.device = Device.objects.create(name="alpha", notes={"a": 1})
        Reading.objects.create(device=cls.device, payload={"n": 1})

    def page(self, url, login=True, **kwargs):
        if login:
            self.client.force_login(self.root)
        response = self.client.get(url, **kwargs)
        self.assertEqual(response.status_code, 200, url)
        return response.content.decode()


class NotAdoptedTests(BrandingCase):
    """Installing the app and even configuring BRANDING changes no page."""

    PAGES = ("/admin/", "/admin/testapp/device/")

    def test_the_setting_alone_renders_exactly_the_stock_admin(self):
        for url in self.PAGES:
            with self.subTest(url=url):
                with branding(adopt=None):
                    configured = self.page(url)
                with override_settings(ADMIN_EXTENSIONS={"COMMANDS_TASK_BACKEND": "commands"}):
                    stock = self.page(url)
                self.assertEqual(normalized(configured), normalized(stock))
                self.assertNotIn("admin-ext-brand", configured)
                self.assertNotIn("branding.css", configured)
                self.assertIsNone(style(configured))

    def test_login_page_too(self):
        with branding(adopt=None):
            html = self.page("/admin/login/", login=False)
        self.assertNotIn("admin-ext-brand", html)
        self.assertIsNone(style(html))


class AdoptedTests(BrandingCase):
    def test_title_and_header_text_are_the_admin_sites_own(self):
        with (
            branding(),
            mock.patch.multiple(admin.site, site_header="Acme operations", site_title="Acme"),
        ):
            html = self.page("/admin/")
        self.assertIn('<div id="site-name"><a href="/admin/">Acme operations</a></div>', html)
        self.assertRegex(html, r"<title>[^<]*\| Acme</title>")

    def test_a_custom_admin_site_keeps_its_own_text(self):
        with branding(), mock.patch.object(restricted_site, "site_header", "Restricted desk"):
            html = self.page("/restricted/")
        self.assertIn(">Restricted desk</a></div>", html)
        self.assertIn('class="admin-ext-brand-logo"', html)

    def test_the_logo_is_a_bounded_static_image_named_after_the_site(self):
        with branding():
            html = self.page("/admin/")
        self.assertIn(
            '<img class="admin-ext-brand-logo" src="/static/testapp/brand-logo.svg"'
            ' alt="Django administration" height="32">',
            html,
        )
        self.assertIn('href="/static/django_extensions_admin/branding.css"', html)
        # Not a link and not a tab stop: the header text stays the one link home.
        self.assertNotRegex(html, r"<a[^>]*>\s*<img class=\"admin-ext-brand-logo\"")
        # Before the stock markup, which is kept whole.
        self.assertLess(html.index("admin-ext-brand-logo"), html.index('id="site-name"'))

    def test_logo_alt_can_be_given_or_emptied(self):
        for alt in ("Acme", ""):
            with self.subTest(alt=alt), branding({**BRANDING, "LOGO_ALT": alt}):
                html = self.page("/admin/")
                self.assertIn(f'alt="{alt}" height="32"', html)

    def test_the_login_page_is_branded_and_keeps_its_theme_toggle(self):
        with branding():
            html = self.page("/admin/login/", login=False)
        self.assertIn('class="admin-ext-brand-logo"', html)
        self.assertIn('<button class="theme-toggle">', html)
        self.assertIsNotNone(style(html))

    def test_no_logo_means_no_image_and_no_stylesheet(self):
        with branding({"COLORS": {"secondary": "#1f3a5f"}}):
            html = self.page("/admin/")
        self.assertNotIn("<img", html.split('id="site-name"')[0].split('id="branding"')[1])
        self.assertNotIn("branding.css", html)
        self.assertIn("--secondary: #1f3a5f;", style(html))

    def test_empty_branding_is_the_stock_admin(self):
        with branding({}):
            adopted = self.page("/admin/")
        stock = self.page("/admin/")
        self.assertEqual(normalized(adopted), normalized(stock))

    def test_a_logo_the_storage_cannot_resolve_leaves_the_header_text(self):
        def fail_for_the_logo(path):
            raise ValueError(f"Missing staticfiles manifest entry for '{path}'")

        with branding(), mock.patch("django.templatetags.static.static", fail_for_the_logo):
            html = self.page("/admin/")
        self.assertNotIn("admin-ext-brand-logo", html)
        self.assertIn('<div id="site-name">', html)

    def test_project_css_comes_after_the_branding_layer(self):
        with branding(adopt="branding_override_templates"):
            html = self.page("/admin/")
        ours = html.index("--secondary: #1f3a5f;")
        theirs = html.index("--header-bg: #4a2040;")
        self.assertLess(ours, theirs)


class StructureTests(BrandingCase):
    """Branding may touch <head> and the header. Every page body stays byte for byte."""

    def assert_same_body(self, url, login=True, method="get", data=None):
        def render():
            if login:
                self.client.force_login(self.root)
            response = getattr(self.client, method)(url, data or {})
            self.assertEqual(response.status_code, 200, url)
            return normalized(
                re.sub(r"<head>.*?</head>", "", response.content.decode(), flags=re.S)
            )

        with branding():
            adopted = render()
        stock = render()
        logo = re.compile(r'\n<img class="admin-ext-brand-logo"[^>]*>\n')
        self.assertEqual(len(logo.findall(adopted)), 1, url)
        # The logo is the one difference in the whole body, <main> included.
        self.assertEqual(logo.sub("", adopted), stock, url)
        self.assertEqual(main(adopted), main(stock), url)

    def test_index(self):
        self.assert_same_body("/admin/")

    def test_changelist_with_actions_list_editable_filters_and_buttons(self):
        self.assert_same_body("/admin/testapp/device/")

    def test_change_form_with_inline_json_widget_and_readonly_json(self):
        self.assert_same_body(f"/admin/testapp/device/{self.device.pk}/change/")

    def test_add_form_with_validation_errors_and_date_widgets(self):
        self.assert_same_body(
            "/admin/testapp/reading/add/",
            method="post",
            data={"recorded_on": "not a date", "payload": "{", "sequence": "x"},
        )

    def test_filtered_changelist_with_range_filters(self):
        self.assert_same_body("/admin/testapp/reading/?value__range__gte=1")

    def test_login(self):
        self.assert_same_body("/admin/login/", login=False)

    def test_command_runner_pages(self):
        self.assert_same_body("/admin/commands/")
        self.assert_same_body("/admin/commands/admin_ext_echo/")


class PaletteTests(BrandingCase):
    def test_each_value_goes_to_the_themes_django_itself_would_give_it(self):
        with branding():
            css = style(self.page("/admin/"))
        rules = dict(re.findall(r"^(.*?) \{ (.*?)\}", css, re.M))
        self.assertEqual(
            rules['html[data-theme="light"], :root'], "--accent: #f2c14e; --secondary: #1f3a5f; "
        )
        # primary has a dark value of Django's own: the light one must not reach it.
        self.assertEqual(rules['html[data-theme="light"]'], "--primary: #5b7fa6; ")
        self.assertIn("@media (prefers-color-scheme: light) { :root { --primary: #5b7fa6; } }", css)
        self.assertEqual(rules['html[data-theme="dark"]'], "--primary: #23384f; ")
        self.assertIn("@media (prefers-color-scheme: dark) { :root { --primary: #23384f; } }", css)
        # Dark rules come last, so a dark value beats an every-theme one in auto mode.
        self.assertLess(css.index("--secondary"), css.index("--primary: #23384f"))

    def test_without_dark_colors_dark_mode_is_djangos(self):
        with branding({"COLORS": {"primary": "#5b7fa6"}}):
            css = style(self.page("/admin/"))
        self.assertNotIn('data-theme="dark"', css)
        self.assertNotIn("prefers-color-scheme: dark", css)
        self.assertNotIn(":root {", css.split("@media")[0])

    def test_invalid_names_and_values_are_never_rendered(self):
        hostile = {
            "COLORS": {
                "secondary": "red; } body { display: none",
                "body-bg": "#000000",
                "accent": "#f2c14e</style><script>alert(1)</script>",
                "primary": "#5b7fa6",
            },
            "DARK_COLORS": "#000",
            "LOGO": "https://cdn.example.invalid/logo.svg",
        }
        with branding(hostile):
            html = self.page("/admin/")
        css = style(html)
        self.assertEqual(re.findall(r"--[a-z-]+: [^;]+;", css), ["--primary: #5b7fa6;"] * 2)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("cdn.example.invalid", html)

    def test_the_dark_sensitive_set_matches_djangos_dark_mode_stylesheet(self):
        base = Path(finders.find("admin/css/base.css")).read_text()
        dark = Path(finders.find("admin/css/dark_mode.css")).read_text()
        defined = set(re.findall(r"--([a-z-]+):", base))
        self.assertLessEqual(PALETTE, defined, "every brand colour is one of Django's")
        self.assertEqual(set(re.findall(r"--([a-z-]+):", dark)) & PALETTE, DARK_SENSITIVE)

    def test_the_style_element_carries_the_csp_nonce(self):
        if find_spec("django.middleware.csp") is None:
            self.skipTest("Django's own CSP support arrived in 6.0")
        from django.utils.csp import CSP

        engines = templates("branding_templates")
        engines[0]["OPTIONS"]["context_processors"].append("django.template.context_processors.csp")
        with override_settings(
            ADMIN_EXTENSIONS={"BRANDING": BRANDING},
            TEMPLATES=engines,
            MIDDLEWARE=[
                *settings.MIDDLEWARE,
                "django.middleware.csp.ContentSecurityPolicyMiddleware",
            ],
            SECURE_CSP={"style-src": [CSP.SELF, CSP.NONCE]},
        ):
            self.client.force_login(self.root)
            response = self.client.get("/admin/")
        nonce = re.search(r"<style nonce=\"([^\"]+)\">", response.content.decode()).group(1)
        self.assertIn(f"'nonce-{nonce}'", response["Content-Security-Policy"])


class CheckTests(TestCase):
    def ids(self, value):
        with override_settings(ADMIN_EXTENSIONS={"BRANDING": value}):
            return [message.id for message in check_branding()]

    def test_silent_without_branding(self):
        with override_settings(ADMIN_EXTENSIONS={}):
            self.assertEqual(check_branding(), [])

    def test_silent_for_a_valid_configuration(self):
        self.assertEqual(self.ids(BRANDING), [])
        self.assertEqual(self.ids({}), [])

    def test_each_mistake_is_reported(self):
        prefix = "django_extensions_admin."
        cases = {
            "not a dict": ["E201"],
            (): ["E201"],
            "": ["E201"],
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(self.ids(value), [prefix + e for e in expected])
        self.assertEqual(self.ids({"LOGO_URL": LOGO}), [prefix + "E202"])
        self.assertEqual(self.ids({"COLORS": ["#fff"]}), [prefix + "E203"])
        self.assertEqual(self.ids({"COLORS": {"body-bg": "#fff"}}), [prefix + "E204"])
        self.assertEqual(self.ids({"COLORS": {"--primary": "#fff"}}), [prefix + "E204"])
        self.assertEqual(self.ids({"DARK_COLORS": {"primary": "blue"}}), [prefix + "E205"])
        self.assertEqual(self.ids({"COLORS": {"primary": "#12345"}}), [prefix + "E205"])
        for logo in (
            "https://example.invalid/l.svg",
            "//example.invalid/l.svg",
            "/l.svg",
            "data:image/svg+xml,<svg/>",
            "",
        ):
            with self.subTest(logo=logo):
                self.assertEqual(self.ids({"LOGO": logo}), [prefix + "E206"])
        self.assertEqual(self.ids({"LOGO_ALT": 3}), [prefix + "E207"])
        self.assertEqual(self.ids({"LOGO": "testapp/missing.svg"}), [prefix + "W201"])

    def test_registered_with_django(self):
        from django.core import checks

        value = {"COMMANDS_TASK_BACKEND": "commands", "BRANDING": {"COLORS": {"body-bg": "#fff"}}}
        with override_settings(ADMIN_EXTENSIONS=value):
            ids = [m.id for m in checks.run_checks() if m.id.startswith("django_extensions_admin.")]
        self.assertEqual(ids, ["django_extensions_admin.E204"])
