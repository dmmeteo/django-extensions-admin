"""Branding in a real browser: the demo's adoption on every surface, theme and width.

The other journeys run on the stock admin (browser_tests/settings.py takes the demo's
adoption out). Here it is put back, so each check below compares the branded admin with
the palette it was given and with the stock admin's own behaviour.
"""

from pathlib import Path
from unittest import mock

from demoapp.models import Device, Reading
from django.conf import settings
from django.contrib import admin
from django.test import override_settings

from .base import BrowserTestCase

ROOT = Path(__file__).resolve().parent.parent
HEADER = "Demo operations"
BRANDED = {**settings.ADMIN_EXTENSIONS, "BRANDING": settings.DEMO_BRANDING}
STOCK_TEMPLATES = settings.TEMPLATES
OVERRIDE_TEMPLATES = [
    {**settings.DEMO_TEMPLATES[0], "DIRS": [ROOT / "tests" / "branding_override_templates"]}
]

# What the demo palette resolves to in each theme. primary, breadcrumbs-bg and link-fg are
# the variables Django itself changes in dark mode; the others stay the same, as in Django.
EXPECTED = {
    "light": {
        "secondary": "#1d4e44",
        "accent": "#f2c14e",
        "primary": "#3f7f70",
        "breadcrumbs-bg": "#143831",
        "link-fg": "#1d6b5a",
        "default-button-bg": "#143831",
    },
    "dark": {
        "secondary": "#1d4e44",
        "accent": "#f2c14e",
        "primary": "#1f4a41",
        # Not in DARK_COLORS: Django's own dark value, var(--primary), not the light one.
        "breadcrumbs-bg": "#1f4a41",
        "link-fg": "#7fd1bd",
        "default-button-bg": "#143831",
    },
}

CSS_VARS = """(names) => Object.fromEntries(names.map(n => [n,
    getComputedStyle(document.documentElement).getPropertyValue('--' + n).trim().toLowerCase()]))"""

# WCAG contrast of an element's text against the first opaque background behind it.
CONTRAST = """(selector) => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const rgb = c => c.match(/[\\d.]+/g).map(Number);
    const opaque = c => { const v = rgb(c); return v.length < 4 || v[3] > 0; };
    let bgEl = el, bg = getComputedStyle(el).backgroundColor;
    while (!opaque(bg) && bgEl.parentElement) {
        bgEl = bgEl.parentElement;
        bg = getComputedStyle(bgEl).backgroundColor;
    }
    const lum = c => {
        const [r, g, b] = rgb(c).slice(0, 3).map(v => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const [a, b] = [lum(getComputedStyle(el).color), lum(bg)].sort((x, y) => y - x);
    return (a + 0.05) / (b + 0.05);
}"""

NO_OVERFLOW = "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"


@override_settings(TEMPLATES=settings.DEMO_TEMPLATES, ADMIN_EXTENSIONS=BRANDED)
class BrandingBrowserTests(BrowserTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The header text is the AdminSite's, exactly as without branding.
        cls.enterClassContext(mock.patch.object(admin.site, "site_header", HEADER))

    def open(self, path, theme=None, login=True, **context_kwargs):
        page = self.new_page(**context_kwargs)
        if theme:
            page.context.add_init_script(f"localStorage.setItem('theme', '{theme}')")
        if login:
            self.login(page)
        page.goto(f"{self.live_server_url}{path}")
        return page

    def device_url(self):
        return f"/admin/demoapp/device/{Device.objects.order_by('pk').first().pk}/change/"

    def assert_branded(self, page):
        self.assertEqual(page.inner_text("#site-name").strip(), HEADER)
        logo = page.locator("#branding img.admin-ext-brand-logo")
        self.assertEqual(logo.get_attribute("alt"), "")
        box = logo.bounding_box()
        self.assertIsNotNone(box, "the logo is not visible")
        self.assertLessEqual(box["height"], 32.5)
        self.assertTrue(
            page.evaluate("() => document.querySelector('.admin-ext-brand-logo').naturalWidth > 0"),
            "the logo did not load",
        )
        colours = page.evaluate(CSS_VARS, ["header-bg", "secondary"])
        self.assertEqual(colours["secondary"], "#1d4e44")
        self.assertEqual(
            page.evaluate(
                "() => getComputedStyle(document.querySelector('#header')).backgroundColor"
            ),
            "rgb(29, 78, 68)",
        )
        self.assertTrue(page.evaluate(NO_OVERFLOW))

    # --- every surface, wide and light -------------------------------------------------

    def test_login_and_index(self):
        page = self.open("/admin/login/", login=False)
        self.assert_branded(page)
        self.assertEqual(page.locator("#branding .theme-toggle").count(), 1)
        self.shot(page, "branding-login")
        self.login(page)
        page.goto(f"{self.live_server_url}/admin/")
        self.assert_branded(page)
        self.shot(page, "branding-index")

    def test_changelist_actions_list_editable_filters_and_buttons_work(self):
        page = self.open("/admin/demoapp/device/")
        self.assert_branded(page)
        self.assertGreater(page.locator(".admin-ext-button").count(), 0)
        self.assertGreater(page.locator("#changelist-filter details").count(), 0)
        self.shot(page, "branding-changelist")

        device = Device.objects.filter(archived=False).order_by("pk").first()
        row = page.locator(f'#result_list tbody tr:has-text("{device.name}")').first
        row.locator('input[name$="-status"]').fill("branded")
        page.click('#changelist-form input[name="_save"]')
        page.wait_for_selector(".messagelist")
        device.refresh_from_db()
        self.assertEqual(device.status, "branded")

        row = page.locator(f'#result_list tbody tr:has-text("{device.name}")').first
        row.locator("input.action-select").check()
        page.select_option('select[name="action"]', "mark_archived")
        page.click('#changelist-form button[name="index"]')
        page.wait_for_selector("#result_list")
        device.refresh_from_db()
        self.assertTrue(device.archived)

    def test_change_form_inline_json_and_buttons_work(self):
        page = self.open(self.device_url())
        self.assert_branded(page)
        page.wait_for_selector(".admin-ext-json-shell")
        self.assertGreater(page.locator(".admin-ext-json-readonly .admin-ext-json-key").count(), 0)
        self.assertGreater(page.locator(".admin-ext-button").count(), 0)
        before = page.locator(".admin-ext-json-shell").count()
        page.click("tr.add-row a")
        page.wait_for_function(
            f"() => document.querySelectorAll('.admin-ext-json-shell').length > {before}"
        )
        self.shot(page, "branding-change-form")

    def test_autocomplete_date_widgets_and_validation_errors_work(self):
        page = self.open("/admin/demoapp/reading/add/")
        self.assert_branded(page)
        device = Device.objects.order_by("pk").first()
        page.click("#id_device + .select2 .select2-selection")
        page.fill(".select2-search__field", device.name)
        page.click(f'.select2-results__option:has-text("{device.name}")')
        self.assertEqual(page.input_value("#id_device"), str(device.pk))

        page.click(".field-recorded_on .datetimeshortcuts a[id^=calendarlink]")
        self.assertTrue(page.locator(".calendarbox").first.is_visible())
        self.shot(page, "branding-calendar")
        page.keyboard.press("Escape")
        page.click(".field-recorded_at .datetimeshortcuts a[id^=clocklink]")
        self.assertTrue(page.locator(".clockbox").first.is_visible())
        page.keyboard.press("Escape")

        before = Reading.objects.count()
        page.fill("#id_recorded_on", "not a date")
        page.click('input[name="_save"]')
        page.wait_for_selector(".errornote")
        self.assertEqual(Reading.objects.count(), before)
        self.assertGreater(page.locator(".field-recorded_on .errorlist").count(), 0)
        self.assert_branded(page)
        self.shot(page, "branding-validation-errors")

    def test_command_runner_pages(self):
        page = self.open("/admin/commands/")
        self.assert_branded(page)
        self.shot(page, "branding-commands-index")
        page.goto(f"{self.live_server_url}/admin/commands/demo_report/")
        self.assert_branded(page)
        self.assertEqual(page.locator('input[type="submit"][value="Run"]').count(), 1)
        self.shot(page, "branding-commands-launch")

    # --- themes ------------------------------------------------------------------------

    def test_light_dark_and_auto_are_each_legible(self):
        for theme, scheme in [
            ("light", "light"),
            ("dark", "dark"),
            ("auto", "light"),
            ("auto", "dark"),
            ("light", "dark"),
            ("dark", "light"),
        ]:
            resolved = scheme if theme == "auto" else theme
            with self.subTest(theme=theme, scheme=scheme):
                page = self.open("/admin/", theme=theme, color_scheme=scheme)
                self.assertEqual(
                    page.evaluate("() => document.documentElement.dataset.theme"), theme
                )
                self.assertEqual(
                    page.evaluate(CSS_VARS, list(EXPECTED[resolved])), EXPECTED[resolved]
                )
                for selector in (
                    "#site-name a",
                    "#user-tools a",
                    ".module caption a",
                    "#content-main td a, #content-main th a",
                ):
                    ratio = page.evaluate(CONTRAST, selector)
                    self.assertGreaterEqual(ratio, 4.5, f"{selector}: {ratio}")
                self.shot(page, f"branding-theme-{theme}-os-{scheme}")
                page.goto(f"{self.live_server_url}{self.device_url()}")
                for selector in ('input[name="_save"]', ".breadcrumbs a", "#user-tools a"):
                    ratio = page.evaluate(CONTRAST, selector)
                    self.assertGreaterEqual(ratio, 4.5, f"{selector}: {ratio}")

    def test_the_theme_toggle_cycles_and_the_palette_follows(self):
        page = self.open("/admin/", color_scheme="light")
        seen = []
        for _ in range(4):
            theme = page.evaluate("() => document.documentElement.dataset.theme")
            resolved = "light" if theme in ("auto", "light") else "dark"
            primary = page.evaluate(CSS_VARS, ["primary"])["primary"]
            self.assertEqual(primary, EXPECTED[resolved]["primary"], theme)
            seen.append(theme)
            page.click("#user-tools .theme-toggle")
        self.assertEqual(set(seen), {"auto", "light", "dark"}, seen)

    def test_project_css_after_the_branding_layer_wins(self):
        with override_settings(TEMPLATES=OVERRIDE_TEMPLATES):
            for theme, scheme, expected in [
                ("light", "light", "rgb(74, 32, 64)"),
                ("dark", "light", "rgb(42, 16, 36)"),
                ("auto", "dark", "rgb(42, 16, 36)"),
            ]:
                with self.subTest(theme=theme, scheme=scheme):
                    page = self.open("/admin/", theme=theme, color_scheme=scheme)
                    header = page.evaluate(
                        "() => getComputedStyle(document.querySelector('#header')).backgroundColor"
                    )
                    self.assertEqual(header, expected)
                    # The branding values the project did not override are still there.
                    self.assertEqual(page.evaluate(CSS_VARS, ["accent"])["accent"], "#f2c14e")
            self.shot(page, "branding-project-override-dark")

    # --- narrow, keyboard --------------------------------------------------------------

    def test_narrow_layouts_do_not_overflow(self):
        for width in (375, 390):
            for scheme in ("light", "dark"):
                viewport = {"width": width, "height": 812}
                page = self.open("/admin/", color_scheme=scheme, viewport=viewport)
                for path in (
                    "/admin/",
                    "/admin/demoapp/device/",
                    self.device_url(),
                    "/admin/commands/demo_report/",
                ):
                    with self.subTest(width=width, scheme=scheme, path=path):
                        page.goto(f"{self.live_server_url}{path}")
                        self.assertTrue(page.evaluate(NO_OVERFLOW))
                        box = page.locator(".admin-ext-brand-logo").bounding_box()
                        self.assertLessEqual(box["width"], width * 0.4 + 1)
                        self.assertLessEqual(box["height"], 32.5)
                self.shot(page, f"branding-narrow-{width}-{scheme}")

    def tab_through_header(self, page, stops=6):
        seen = []
        for _ in range(stops):
            page.keyboard.press("Tab")
            seen.append(
                page.evaluate(
                    """() => { const el = document.activeElement;
                        return [el.tagName, el.id, el.className,
                                (el.textContent || el.value || '').trim().slice(0, 30)]; }"""
                )
            )
        return seen

    def test_keyboard_order_is_the_stock_admins_and_focus_is_visible(self):
        page = self.open("/admin/")
        branded = self.tab_through_header(page)
        self.assertNotIn("IMG", [stop[0] for stop in branded])
        page.goto(f"{self.live_server_url}/admin/")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        focused = page.evaluate(
            """() => { const el = document.activeElement, s = getComputedStyle(el);
                return [el.closest('#site-name') !== null, s.outlineStyle,
                        s.textDecorationLine]; }"""
        )
        self.assertTrue(focused[0], "the second stop is the site name link")
        self.assertTrue(focused[1] != "none" or "underline" in focused[2], focused)
        self.shot(page, "branding-focus-site-name")

        with override_settings(TEMPLATES=STOCK_TEMPLATES):
            stock = self.tab_through_header(self.open("/admin/"))
        self.assertEqual(branded, stock)

    # --- degradation -------------------------------------------------------------------

    def test_a_missing_logo_leaves_the_header_text(self):
        page = self.new_page()
        page.route("**/demoapp/logo.svg", lambda route: route.abort())
        self.login(page)
        self.assertEqual(page.inner_text("#site-name").strip(), HEADER)
        self.assertTrue(page.locator("#site-name a").is_visible())
        self.assertTrue(page.evaluate(NO_OVERFLOW))
        # A decorative image that fails shows nothing: no alt text, no broken-image box.
        width = page.evaluate(
            "() => document.querySelector('.admin-ext-brand-logo').getBoundingClientRect().width"
        )
        self.assertEqual(width, 0)
        self.shot(page, "branding-missing-logo")

    def test_a_missing_branding_stylesheet_still_bounds_the_logo(self):
        page = self.new_page(viewport={"width": 375, "height": 812})
        page.route("**/django_extensions_admin/branding.css", lambda route: route.abort())
        self.login(page)
        box = page.locator(".admin-ext-brand-logo").bounding_box()
        self.assertLessEqual(box["height"], 32.5)
        self.assertEqual(page.inner_text("#site-name").strip(), HEADER)
        self.assertTrue(page.evaluate(NO_OVERFLOW))
        self.shot(page, "branding-missing-stylesheet")

    def test_no_logo_and_no_palette_is_the_stock_header(self):
        with override_settings(ADMIN_EXTENSIONS={**BRANDED, "BRANDING": {}}):
            page = self.open("/admin/")
            self.assertEqual(page.locator(".admin-ext-brand-logo").count(), 0)
            self.assertEqual(
                page.evaluate(
                    "() => getComputedStyle(document.querySelector('#header')).backgroundColor"
                ),
                "rgb(65, 118, 144)",
            )
            self.assertEqual(page.inner_text("#site-name").strip(), HEADER)
