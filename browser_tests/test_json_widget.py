"""What the JSON widget does in a real browser - including when parts of it fail."""

from .base import BrowserTestCase

FIELD = "textarea[data-admin-ext-json]"
PAYLOAD_FIELD = "#id_payload"


class JSONWidgetBrowserTests(BrowserTestCase):
    def open_reading(self, label, **context_kwargs):
        page = self.new_page(**context_kwargs)
        self.login(page)
        page.goto(self.reading_change_url(label))
        return page

    def test_overlay_is_aligned_with_the_textarea(self):
        """The caret lives in the textarea and the colours in the <pre> underneath, so
        the two boxes must measure identically or the text visibly drifts."""
        page = self.open_reading("nested + typical")
        page.wait_for_selector(".admin-ext-json-shell")
        # A long line makes both boxes overflow horizontally, so scrollWidth reports the
        # width of the text itself rather than each box's own viewport (the textarea's is
        # narrower by its scrollbar, which is cosmetic and not caret drift).
        page.fill(PAYLOAD_FIELD, '{"line": "' + "m" * 300 + '"}')
        page.wait_for_timeout(300)
        metrics = page.evaluate(
            """() => {
                const ta = document.querySelector('#id_payload');
                const pre = ta.closest('.admin-ext-json-shell').querySelector('pre');
                const mirrored = ['fontFamily','fontSize','fontWeight','lineHeight',
                    'letterSpacing','paddingTop','paddingLeft','paddingRight',
                    'paddingBottom','tabSize','borderLeftWidth','borderTopWidth'];
                const a = getComputedStyle(ta), b = getComputedStyle(pre);
                return {
                    differing: mirrored.filter(k => a[k] !== b[k]),
                    scrollWidth: [ta.scrollWidth, pre.scrollWidth],
                    scrollHeight: [ta.scrollHeight, pre.scrollHeight],
                    text: pre.textContent === ta.value,
                };
            }"""
        )
        self.assertEqual(metrics["differing"], [])
        # scrollWidth is reported as a rounded integer, so a single pixel over ~2200px of
        # text is rounding, not drift. Anything larger means the boxes disagree.
        self.assertLessEqual(
            abs(metrics["scrollWidth"][0] - metrics["scrollWidth"][1]),
            1,
            metrics["scrollWidth"],
        )
        self.assertEqual(metrics["scrollHeight"][0], metrics["scrollHeight"][1])
        self.assertTrue(metrics["text"])
        page.reload()
        page.wait_for_selector(".admin-ext-json-shell")
        self.shot(page, "json-editor-light")

    def test_highlighting_is_applied(self):
        page = self.open_reading("nested + typical")
        page.wait_for_selector(".admin-ext-json-key")
        self.assertGreater(page.locator(".admin-ext-json-key").count(), 0)
        self.assertGreater(page.locator(".admin-ext-json-string").count(), 0)
        self.assertGreater(page.locator(".admin-ext-json-number").count(), 0)

    def test_horizontal_scroll_stays_in_sync(self):
        page = self.open_reading("nested + typical")
        page.wait_for_selector(".admin-ext-json-shell")
        page.fill(PAYLOAD_FIELD, '{"line": "' + "y" * 400 + '"}')
        offsets = page.evaluate(
            """() => {
                const ta = document.querySelector('#id_payload');
                ta.scrollLeft = 220;
                ta.dispatchEvent(new Event('scroll'));
                const pre = ta.closest('.admin-ext-json-shell').querySelector('pre');
                return [ta.scrollLeft, pre.scrollLeft];
            }"""
        )
        self.assertEqual(offsets[0], offsets[1])
        self.assertGreater(offsets[0], 0)

    def test_invalid_input_is_reported_and_marked(self):
        page = self.open_reading("nested + typical")
        page.wait_for_selector(".admin-ext-json-shell")
        page.fill(PAYLOAD_FIELD, '{"a": 1,}')
        page.wait_for_selector(".admin-ext-json-mark")
        self.assertIn("admin-ext-json--invalid", page.get_attribute(PAYLOAD_FIELD, "class"))
        self.assertNotEqual(page.inner_text(".admin-ext-json-error").strip(), "")
        self.shot(page, "json-invalid-input")

    def test_invalid_input_survives_a_failed_save(self):
        page = self.open_reading("nested + typical")
        page.fill(PAYLOAD_FIELD, '{"a": 1,}')
        page.click('input[name="_continue"]')
        page.wait_for_selector(".errornote, ul.errorlist")
        self.assertEqual(page.input_value(PAYLOAD_FIELD).strip(), '{"a": 1,}')
        self.shot(page, "json-invalid-after-save")

    def test_format_button_is_lossless_for_numbers_javascript_cannot_hold(self):
        page = self.open_reading("big numbers (fidelity)")
        page.wait_for_selector(".admin-ext-json-shell")
        compact = '{"beyond_double":9007199254740993,"exp":1.0E2,"big":123456789012345678901234}'
        page.fill(PAYLOAD_FIELD, compact)
        page.click(".admin-ext-json-format")
        value = page.input_value(PAYLOAD_FIELD)
        self.assertIn("9007199254740993", value)
        self.assertIn("1.0E2", value)
        self.assertIn("123456789012345678901234", value)
        self.assertIn("\n", value)
        # JSON.parse/stringify would have produced 9007199254740992 and 100.
        self.assertNotIn("9007199254740992", value)

    def test_format_keeps_native_undo(self):
        page = self.open_reading("nested + typical")
        page.wait_for_selector(".admin-ext-json-shell")
        compact = '{"a":1,"b":[2,3]}'
        page.fill(PAYLOAD_FIELD, compact)
        page.click(".admin-ext-json-format")
        self.assertIn("\n", page.input_value(PAYLOAD_FIELD))
        page.focus(PAYLOAD_FIELD)
        page.keyboard.press("Control+z")
        self.assertEqual(page.input_value(PAYLOAD_FIELD), compact)

    def test_no_automatic_reformat_on_blur_by_default(self):
        page = self.open_reading("nested + typical")
        page.wait_for_selector(".admin-ext-json-shell")
        compact = '{"a":1}'
        page.fill(PAYLOAD_FIELD, compact)
        page.click("#id_label")
        page.wait_for_timeout(300)
        self.assertEqual(page.input_value(PAYLOAD_FIELD), compact)

    def test_html_in_values_is_not_executed(self):
        page = self.open_reading("html-looking strings (escaping)")
        page.wait_for_selector(".admin-ext-json-shell")
        self.assertEqual(page.locator("img[onerror]").count(), 0)
        self.assertEqual(page.locator("textarea b").count(), 0)
        self.assertIn("<script>", page.input_value(PAYLOAD_FIELD))
        self.shot(page, "json-escaping")

    def test_oversized_payload_falls_back_to_a_plain_field(self):
        page = self.open_reading("large payload (plain mode)")
        page.wait_for_selector(FIELD)
        state = page.evaluate(
            """() => {
                const ta = document.querySelector('#id_payload');
                const shell = ta.closest('.admin-ext-json-shell');
                return {
                    plain: shell ? shell.classList.contains('admin-ext-json-shell--plain') : null,
                    length: ta.value.length,
                    color: getComputedStyle(ta).color,
                };
            }"""
        )
        self.assertTrue(state["plain"])
        self.assertGreater(state["length"], 100000)
        self.assertNotEqual(state["color"], "rgba(0, 0, 0, 0)")
        self.shot(page, "json-oversized-plain")

    def test_field_stays_readable_when_the_stylesheet_is_missing(self):
        """The script only hides the textarea's own text once it has proof the
        stylesheet loaded; without it there must be no overlay at all."""
        page = self.new_page()
        page.route("**/django_extensions_admin/json-widget.css", lambda route: route.abort())
        self.login(page)
        page.goto(self.reading_change_url("nested + typical"))
        page.wait_for_selector(FIELD)
        page.wait_for_timeout(300)
        state = page.evaluate(
            """() => {
                const ta = document.querySelector('#id_payload');
                return {
                    shell: !!ta.closest('.admin-ext-json-shell'),
                    color: getComputedStyle(ta).color,
                    value: ta.value.length,
                };
            }"""
        )
        self.assertFalse(state["shell"])
        self.assertNotEqual(state["color"], "rgba(0, 0, 0, 0)")
        self.assertGreater(state["value"], 0)
        self.shot(page, "json-no-css")

    def test_field_is_usable_without_javascript(self):
        page = self.open_reading("nested + typical", java_script_enabled=False)
        page.wait_for_selector(FIELD)
        box = page.locator(PAYLOAD_FIELD).bounding_box()
        self.assertIsNotNone(box)
        self.assertGreater(box["height"], 20)
        self.assertIn("request", page.input_value(PAYLOAD_FIELD))
        self.assertEqual(page.locator(".admin-ext-json-shell").count(), 0)
        page.fill(PAYLOAD_FIELD, '{"typed": true}')
        page.click('input[name="_save"]')
        page.wait_for_selector(".messagelist")
        self.shot(page, "json-no-javascript")
        from demoapp.models import Reading

        self.assertEqual(Reading.objects.get(label="nested + typical").payload, {"typed": True})

    def test_dark_theme_renders(self):
        page = self.open_reading("unicode", color_scheme="dark")
        page.wait_for_selector(".admin-ext-json-shell")
        colour = page.evaluate(
            """() => getComputedStyle(document.querySelector('.admin-ext-json-key')).color"""
        )
        self.assertTrue(colour.startswith("rgb"))
        self.shot(page, "json-editor-dark")

    def test_unicode_is_rendered_readably(self):
        page = self.open_reading("unicode")
        page.wait_for_selector(".admin-ext-json-shell")
        value = page.input_value(PAYLOAD_FIELD)
        for sample in ("Персона", "日本語", "🚀"):
            self.assertIn(sample, value)

    def test_readonly_rendering_on_a_device(self):
        page = self.new_page()
        self.login(page)
        from demoapp.models import Device

        device = Device.objects.order_by("pk").first()
        page.goto(f"{self.live_server_url}/admin/demoapp/device/{device.pk}/change/")
        page.wait_for_selector(".admin-ext-json-readonly")
        self.assertGreater(page.locator(".admin-ext-json-readonly .admin-ext-json-key").count(), 0)
        self.shot(page, "json-readonly")

    def test_inline_row_added_after_load_is_initialised(self):
        page = self.new_page()
        self.login(page)
        from demoapp.models import Device

        device = Device.objects.order_by("pk").first()
        page.goto(f"{self.live_server_url}/admin/demoapp/device/{device.pk}/change/")
        page.wait_for_selector(".admin-ext-json-shell")
        before = page.locator(".admin-ext-json-shell").count()
        page.click("tr.add-row a")
        page.wait_for_function(
            f"() => document.querySelectorAll('.admin-ext-json-shell').length > {before}"
        )
        after = page.locator(".admin-ext-json-shell").count()
        self.assertGreater(after, before)
        # The hidden __prefix__ template must never be initialised.
        self.assertEqual(
            page.evaluate(
                """() => document.querySelectorAll(
                    'textarea[id*="__prefix__"][data-admin-ext-ready]').length"""
            ),
            0,
        )
        self.shot(page, "json-inline-added")
