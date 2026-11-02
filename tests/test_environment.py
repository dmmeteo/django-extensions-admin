"""The environment indicator: a name turns it on, anything it renders is validated or escaped."""

import re

from django.contrib.auth.models import User
from django.core import checks
from django.test import TestCase, override_settings

from django_extensions_admin.environment.indicator import check_environment, resolve


def environment(value):
    return override_settings(ADMIN_EXTENSIONS={"ENVIRONMENT": value})


class IndicatorPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("root", "root@example.com", "pw")
        self.client.force_login(self.user)

    def page(self, url="/admin/"):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # CSRF tokens legitimately differ between two renders.
        return re.sub(
            r'(name="csrfmiddlewaretoken" value=")[^"]+', r"\1-", response.content.decode()
        )

    def test_unset_and_empty_render_the_stock_admin(self):
        stock = self.page()
        self.assertNotIn("admin-ext-environment", stock)
        for value in ("", "   ", {"NAME": ""}, None):
            with self.subTest(value=value), environment(value):
                self.assertEqual(self.page(), stock)

    @environment("Staging")
    def test_a_plain_name_shows_a_red_five_pixel_line_and_a_badge_at_the_top(self):
        page = self.page()
        self.assertIn('<div class="admin-ext-environment" data-position="top"', page)
        self.assertIn('<span class="admin-ext-environment-name">Staging</span>', page)
        self.assertIn("--admin-ext-env-color:#ba2121;", page)
        self.assertIn("--admin-ext-env-height:5px;", page)
        self.assertIn("--admin-ext-env-text:#ffffff;", page)
        # Above Django's own header, which stays as it was.
        self.assertLess(
            page.index("admin-ext-environment-name"), page.index('<header id="header">')
        )

    @environment({"NAME": "Production", "COLOR": "#FFEB3B", "POSITION": "bottom", "HEIGHT": 8})
    def test_overrides_place_it_at_the_bottom_with_readable_text(self):
        page = self.page()
        self.assertIn('data-position="bottom"', page)
        self.assertGreater(
            page.index("admin-ext-environment-name"), page.index('<footer id="footer">')
        )
        self.assertIn("--admin-ext-env-color:#ffeb3b;", page)
        self.assertIn("--admin-ext-env-text:#000000;", page)
        self.assertIn("--admin-ext-bottom-inset:8px;", page)

    @environment('<script>alert("x")</script>')
    def test_the_name_is_escaped(self):
        page = self.page()
        self.assertNotIn('<script>alert("x")</script>', page)
        self.assertIn("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;", page)

    @environment(
        {"NAME": "QA", "COLOR": "red;}body{display:none", "POSITION": "left", "HEIGHT": "99px"}
    )
    def test_invalid_values_never_reach_the_page_and_the_name_still_shows(self):
        page = self.page()
        self.assertNotIn("display:none", page)
        self.assertNotIn("99px", page)
        self.assertIn('data-position="top"', page)
        self.assertIn("--admin-ext-env-color:#ba2121;", page)
        self.assertIn(">QA</span>", page)

    @environment({"NAME": "Staging", "POSITION": "bottom"})
    def test_popups_show_no_indicator_in_either_position(self):
        self.assertNotIn("admin-ext-environment-name", self.page("/admin/auth/user/add/?_popup=1"))
        with environment("Staging"):
            self.assertNotIn(
                "admin-ext-environment-name", self.page("/admin/auth/user/add/?_popup=1")
            )

    @environment("Staging")
    def test_the_login_page_shows_it_too(self):
        self.client.logout()
        self.assertIn(">Staging</span>", self.page("/admin/login/"))

    @environment("Staging")
    def test_a_csp_nonce_reaches_the_style_element(self):
        from django.template.loader import render_to_string

        indicator = resolve()
        html = render_to_string(
            "django_extensions_admin/environment/style.html",
            {"environment": indicator, "csp_nonce": "abc123"},
        )
        self.assertIn('<style nonce="abc123">', html)


class IndicatorCheckTests(TestCase):
    def ids(self):
        return [m.id for m in check_environment()]

    def test_valid_settings_report_nothing(self):
        for value in (
            "",
            "Staging",
            {"NAME": "Prod", "COLOR": "#123", "POSITION": "bottom", "HEIGHT": 2},
        ):
            with self.subTest(value=value), environment(value):
                self.assertEqual(self.ids(), [])

    def test_each_invalid_value_has_its_own_error(self):
        for raw, expected in [
            (42, ["django_extensions_admin.E301"]),
            ("   ", ["django_extensions_admin.E302"]),
            ({"NAME": "x", "SIZE": 3}, ["django_extensions_admin.E303"]),
            ({"NAME": "x", "COLOR": "red"}, ["django_extensions_admin.E304"]),
            ({"NAME": "x", "POSITION": "left"}, ["django_extensions_admin.E305"]),
            ({"NAME": "x", "HEIGHT": 40}, ["django_extensions_admin.E306"]),
            ({"NAME": "x", "HEIGHT": True}, ["django_extensions_admin.E306"]),
        ]:
            with self.subTest(raw=raw), environment(raw):
                self.assertEqual(self.ids(), expected)

    @environment({"NAME": "x", "COLOR": "red"})
    def test_the_check_is_registered(self):
        ids = [m.id for m in checks.run_checks()]
        self.assertIn("django_extensions_admin.E304", ids)
