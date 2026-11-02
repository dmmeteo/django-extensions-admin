"""The changelist already has a form of its own; buttons must not nest one inside it."""

from html.parser import HTMLParser

from django.contrib.auth.models import User
from django.test import TestCase

from .testapp.models import Device


class FormNestingParser(HTMLParser):
    """Records form depth and where every submit control sits."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.max_depth = 0
        self.form_ids = []
        self.open_form_ids = []
        self.nested = []
        self.submits_inside_changelist_form = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.depth += 1
            self.max_depth = max(self.max_depth, self.depth)
            form_id = attrs.get("id")
            self.form_ids.append(form_id)
            if self.depth > 1:
                self.nested.append(form_id)
            self.open_form_ids.append(form_id)
        elif tag in ("button", "input") and "changelist-form" in self.open_form_ids:
            if attrs.get("type") == "submit":
                self.submits_inside_changelist_form.append(attrs)

    def handle_endtag(self, tag):
        if tag == "form":
            self.depth = max(0, self.depth - 1)
            if self.open_form_ids:
                self.open_form_ids.pop()


class ChangelistMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser("root", "root@example.invalid", "pw")
        Device.objects.create(name="alpha", region="eu")

    def parse_changelist(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/admin/testapp/device/")
        self.assertEqual(response.status_code, 200)
        parser = FormNestingParser()
        parser.feed(response.content.decode())
        return response.content.decode(), parser

    def test_no_nested_forms_on_the_changelist(self):
        _, parser = self.parse_changelist()
        self.assertEqual(parser.nested, [])
        self.assertEqual(parser.max_depth, 1)

    def test_the_action_form_exists_and_is_separate(self):
        _, parser = self.parse_changelist()
        self.assertIn("admin-ext-action-form", parser.form_ids)
        self.assertIn("changelist-form", parser.form_ids)

    def test_row_buttons_target_the_external_form_by_id(self):
        _, parser = self.parse_changelist()
        row_submits = [
            attrs
            for attrs in parser.submits_inside_changelist_form
            if "admin-ext-button--row" in (attrs.get("class") or "")
        ]
        self.assertTrue(row_submits, "expected row buttons inside the changelist form")
        for attrs in row_submits:
            self.assertEqual(attrs.get("form"), "admin-ext-action-form")
            self.assertEqual(attrs.get("formmethod"), "post")
            self.assertIn("/admin-ext/", attrs.get("formaction", ""))

    def test_bulk_action_controls_are_still_there(self):
        html, _ = self.parse_changelist()
        self.assertIn('name="action"', html)
        self.assertIn('name="_save"', html)  # list_editable save button

    def test_no_nested_forms_on_the_change_form(self):
        device = Device.objects.create(name="beta")
        self.client.force_login(self.superuser)
        response = self.client.get(f"/admin/testapp/device/{device.pk}/change/")
        parser = FormNestingParser()
        parser.feed(response.content.decode())
        self.assertEqual(parser.nested, [])

    def test_no_nested_forms_on_the_confirmation_page(self):
        device = Device.objects.create(name="gamma")
        self.client.force_login(self.superuser)
        response = self.client.post(f"/admin/testapp/device/{device.pk}/admin-ext/archive/")
        parser = FormNestingParser()
        parser.feed(response.content.decode())
        self.assertEqual(parser.nested, [])
