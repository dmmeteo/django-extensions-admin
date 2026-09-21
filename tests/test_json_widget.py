"""The widget swaps rendering only: the form field, validation and storage stay native."""

import json

from django import forms
from django.contrib import admin
from django.contrib.staticfiles import finders
from django.forms import JSONField as JSONFormField
from django.test import RequestFactory, TestCase, override_settings

from django_extensions_admin import PrettyJSONWidget
from django_extensions_admin.jsonwidget.readonly import render_json

from .testapp.models import Device


class FormatValueTests(TestCase):
    def setUp(self):
        self.widget = PrettyJSONWidget()

    def test_indents_compact_json(self):
        self.assertEqual(
            self.widget.format_value('{"a": 1}'),
            '{\n  "a": 1\n}',
        )

    def test_returns_invalid_input_unchanged(self):
        broken = '{"model": "x",}'
        self.assertEqual(self.widget.format_value(broken), broken)

    def test_passes_through_empty_values(self):
        self.assertIsNone(self.widget.format_value(None))
        self.assertEqual(self.widget.format_value(""), "")

    def test_skips_oversized_payloads(self):
        widget = PrettyJSONWidget(max_pretty_chars=50)
        oversized = json.dumps({"blob": "x" * 100})
        self.assertEqual(widget.format_value(oversized), oversized)

    def test_oversized_payload_still_renders_its_text(self):
        widget = PrettyJSONWidget(max_pretty_chars=50)
        oversized = json.dumps({"blob": "x" * 100})
        html = widget.render("payload", oversized, attrs={"id": "id_payload"})
        self.assertIn("x" * 100, html)

    def test_widget_attrs_carry_configuration(self):
        widget = PrettyJSONWidget(max_pretty_chars=1234, indent=4, reformat_on_blur=True)
        html = widget.render("payload", "{}", attrs={"id": "id_payload"})
        self.assertIn('data-admin-ext-json="1"', html)
        self.assertIn('data-admin-ext-max-chars="1234"', html)
        self.assertIn('data-admin-ext-indent="4"', html)
        self.assertIn('data-admin-ext-blur-format="1"', html)

    def test_blur_format_attribute_absent_by_default(self):
        html = PrettyJSONWidget().render("payload", "{}", attrs={"id": "id_payload"})
        self.assertNotIn("data-admin-ext-blur-format", html)

    def test_html_in_value_is_escaped(self):
        html = PrettyJSONWidget().render(
            "payload", '{"x": "</textarea><img src=q onerror=alert(1)>"}', attrs={"id": "p"}
        )
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_media_lists_both_assets(self):
        media = str(PrettyJSONWidget().media)
        self.assertIn("django_extensions_admin/json-widget.css", media)
        self.assertIn("django_extensions_admin/json-widget.js", media)

    def test_assets_are_discoverable_by_staticfiles(self):
        for asset in (
            "django_extensions_admin/json-widget.css",
            "django_extensions_admin/json-widget.js",
        ):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))


class NativeValidationTests(TestCase):
    """Nothing about forms.JSONField changes, including how it reports bad input."""

    def form_class(self):
        class DeviceForm(forms.ModelForm):
            class Meta:
                model = Device
                fields = ["name", "config"]
                widgets = {"config": PrettyJSONWidget()}

        return DeviceForm

    def test_form_field_type_is_untouched(self):
        form = self.form_class()()
        self.assertIsInstance(form.fields["config"], JSONFormField)
        self.assertIsInstance(form.fields["config"].widget, PrettyJSONWidget)

    def test_invalid_json_is_rejected_by_the_native_field(self):
        form = self.form_class()(data={"name": "d", "config": '{"a": }'})
        self.assertFalse(form.is_valid())
        self.assertIn("config", form.errors)

    def test_invalid_input_survives_redisplay(self):
        import html as html_module
        import re

        broken = '{"a": 1,}'
        form = self.form_class()(data={"name": "d", "config": broken})
        self.assertFalse(form.is_valid())
        rendered = form.as_p()
        body = re.search(r"<textarea[^>]*>(.*?)</textarea>", rendered, re.S).group(1)
        # Escaped in the HTML, byte-identical once unescaped: the user gets their own
        # text back instead of an empty box.
        self.assertNotIn(broken, rendered)
        self.assertEqual(html_module.unescape(body).strip("\n"), broken)

    def test_valid_json_saves_through_the_native_field(self):
        form = self.form_class()(data={"name": "d", "config": '{"a": [1, 2]}'})
        self.assertTrue(form.is_valid())
        device = form.save()
        device.refresh_from_db()
        self.assertEqual(device.config, {"a": [1, 2]})

    def test_stored_value_redisplays_indented(self):
        device = Device.objects.create(name="d", config={"a": {"b": 1}})
        form = self.form_class()(instance=device)
        self.assertIn("{\n  &quot;a&quot;: {\n    &quot;b&quot;: 1\n  }\n}", form.as_p())

    def test_bom_is_stripped_before_native_validation(self):
        form = self.form_class()(data={"name": "d", "config": '﻿{"a": 1}'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_database_round_trip_is_the_native_one(self):
        """Documented limitation: the widget preserves text, a save does not.

        Saving goes through forms.JSONField and the database, so duplicate keys collapse
        and numbers become Python/JSON numbers. The widget never promises otherwise.
        """
        form = self.form_class()(data={"name": "d", "config": '{"a": 1, "a": 2}'})
        self.assertTrue(form.is_valid())
        device = form.save()
        device.refresh_from_db()
        self.assertEqual(device.config, {"a": 2})


class AdminIntegrationTests(TestCase):
    def test_admin_uses_the_widget_for_a_json_field(self):
        model_admin = admin.site._registry[Device]
        db_field = Device._meta.get_field("config")
        form_field = model_admin.formfield_for_dbfield(db_field, request=RequestFactory().get("/"))
        self.assertIsInstance(form_field, JSONFormField)
        self.assertIsInstance(form_field.widget, PrettyJSONWidget)


@override_settings(ADMIN_EXTENSIONS={"JSON_INDENT": 2})
class ReadonlyRenderingTests(TestCase):
    def test_renders_highlighted_pre(self):
        html = render_json({"a": 1})
        self.assertIn("admin-ext-json-readonly", html)
        self.assertIn("admin-ext-json-key", html)
        self.assertIn("admin-ext-json-number", html)

    def test_escapes_html(self):
        html = render_json({"x": "<script>alert(1)</script>"})
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_escapes_html_in_keys(self):
        html = render_json({"<b>k</b>": 1})
        self.assertNotIn("<b>", html)

    def test_none_renders_a_placeholder(self):
        self.assertIn("admin-ext-json-empty", render_json(None))

    def test_invalid_json_string_is_rendered_as_text(self):
        html = render_json('{"a": }')
        self.assertIn("{&quot;a&quot;: }", html)

    def test_oversized_value_is_not_highlighted(self):
        html = render_json({"blob": "x" * 200}, max_pretty_chars=50)
        self.assertIn("admin-ext-json-readonly--plain", html)

    def test_readonly_field_shows_up_on_the_change_form(self):
        from django.contrib.auth.models import User

        user = User.objects.create_superuser("root", "root@example.invalid", "pw")
        device = Device.objects.create(name="d", notes={"note": "hello"})
        self.client.force_login(user)
        response = self.client.get(f"/admin/testapp/device/{device.pk}/change/")
        self.assertContains(response, "admin-ext-json-readonly")
        self.assertContains(response, "hello")
