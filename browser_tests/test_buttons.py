"""Buttons in a real browser, on a changelist that also has bulk actions and
list_editable - the case where a nested <form> would silently break."""

from demoapp.models import Device

from .base import BrowserTestCase

CHANGELIST = "/admin/demoapp/device/"


class ButtonBrowserTests(BrowserTestCase):
    def open_changelist(self, query="", user="demo", password="demo"):
        page = self.new_page()
        self.login(page, user, password)
        page.goto(f"{self.live_server_url}{CHANGELIST}{query}")
        page.wait_for_selector("#result_list")
        return page

    def test_changelist_markup_has_no_nested_forms(self):
        """Browsers drop a nested <form> outright, so assert on the parsed DOM."""
        page = self.open_changelist()
        nested = page.evaluate("() => Array.from(document.querySelectorAll('form form')).length")
        self.assertEqual(nested, 0)
        owners = page.evaluate(
            """() => Array.from(document.querySelectorAll('.admin-ext-button--row'))
                .map(b => b.form ? b.form.id : null)"""
        )
        self.assertTrue(owners)
        self.assertTrue(all(owner == "admin-ext-action-form" for owner in owners), owners)
        self.shot(page, "buttons-changelist")

    def test_row_button_runs_through_the_confirmation_page(self):
        page = self.open_changelist()
        device = Device.objects.filter(archived=False).order_by("pk").first()
        row = page.locator(f'#result_list tbody tr:has-text("{device.name}")').first
        row.locator(".admin-ext-button--row").first.click()
        page.wait_for_selector(".admin-ext-confirm-question")
        self.shot(page, "buttons-confirm")
        page.click('input[value="Yes, I am sure"]')
        page.wait_for_selector("#result_list")
        device.refresh_from_db()
        self.assertTrue(device.archived)
        self.assertIn("Archived", page.inner_text(".messagelist"))
        self.shot(page, "buttons-after-row-action")

    def test_row_button_does_not_submit_pending_list_editable_edits(self):
        """The button owns a separate form, so half-finished inline edits are not saved."""
        page = self.open_changelist()
        device = Device.objects.filter(archived=False).order_by("pk").first()
        original_status = device.status
        row = page.locator(f'#result_list tbody tr:has-text("{device.name}")').first
        row.locator('input[name$="-status"]').fill("typed-but-not-saved")
        row.locator(".admin-ext-button--row").first.click()
        page.wait_for_selector(".admin-ext-confirm-question")
        page.click('input[value="Yes, I am sure"]')
        page.wait_for_selector("#result_list")
        device.refresh_from_db()
        self.assertTrue(device.archived)
        self.assertEqual(device.status, original_status)

    def test_bulk_actions_still_work_next_to_the_buttons(self):
        page = self.open_changelist()
        page.check("#action-toggle")
        page.select_option('select[name="action"]', "mark_archived")
        page.click('button[name="index"]')
        page.wait_for_selector("#result_list")
        self.assertEqual(Device.objects.filter(archived=False).count(), 0)

    def test_the_action_dropdown_never_lists_a_button(self):
        page = self.open_changelist()
        options = page.eval_on_selector_all(
            'select[name="action"] option', "nodes => nodes.map(n => n.value)"
        )
        self.assertNotIn("ping_all", options)
        self.assertNotIn("archive", options)
        self.assertIn("mark_archived", options)

    def test_toolbar_button_returns_to_the_filtered_list(self):
        region = Device.objects.order_by("pk").first().region
        page = self.open_changelist(f"?region={region}")
        total = Device.objects.count()
        page.click('button:has-text("Ping all devices")')
        page.wait_for_selector("#result_list")
        self.assertIn(f"region={region}", page.url)
        self.assertIn(f"Pinged {total} devices", page.inner_text(".messagelist"))
        self.assertEqual(Device.objects.filter(status="pinged").count(), total)
        self.shot(page, "buttons-filtered-result")

    def test_report_button_shows_its_result(self):
        page = self.open_changelist()
        page.click('button:has-text("Count by region")')
        page.wait_for_selector(".messagelist")
        self.assertIn("eu-west", page.inner_text(".messagelist"))

    def test_object_button_on_the_change_form(self):
        device = Device.objects.order_by("pk").first()
        page = self.new_page()
        self.login(page)
        page.goto(f"{self.live_server_url}{CHANGELIST}{device.pk}/change/")
        page.click('button:has-text("Run diagnostics")')
        page.wait_for_selector(".messagelist")
        device.refresh_from_db()
        self.assertEqual(device.status, "diagnosed")
        self.shot(page, "buttons-change-form")

    def test_one_handler_returns_to_whichever_page_it_was_used_from(self):
        """`archive` is placed on the change form and in every row: one endpoint, two
        sensible destinations."""
        device = Device.objects.filter(archived=False).order_by("pk").first()
        page = self.new_page()
        self.login(page)
        page.goto(f"{self.live_server_url}{CHANGELIST}{device.pk}/change/")
        page.click('button:has-text("Archive")')
        page.wait_for_selector(".admin-ext-confirm-question")
        page.click('input[value="Yes, I am sure"]')
        page.wait_for_selector(".messagelist")
        device.refresh_from_db()
        self.assertTrue(device.archived)
        self.assertIn(f"{CHANGELIST}{device.pk}/change/", page.url)

    def test_denied_button_is_not_offered_to_the_operator(self):
        page = self.open_changelist(user="operator", password="operator")
        self.assertEqual(page.locator('button:has-text("Purge archived")').count(), 0)
        # ...and the endpoint refuses it even when the form is submitted by hand.
        status = page.evaluate(
            """async (url) => {
                const token = document.querySelector('[name=csrfmiddlewaretoken]').value;
                const body = new URLSearchParams({csrfmiddlewaretoken: token,
                                                  _admin_ext_confirmed: '1'});
                const response = await fetch(url, {method: 'POST', body,
                                                   headers: {'X-CSRFToken': token}});
                return response.status;
            }""",
            f"{self.live_server_url}{CHANGELIST}admin-ext/purge_archived/",
        )
        self.assertEqual(status, 403)
        self.shot(page, "buttons-operator-view")
