"""Buttons: rendering is a hint, the endpoint is the authority."""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse

from .testapp.models import Device

CHANGELIST = "/admin/testapp/device/"


def button_url(name, pk=None):
    if pk is None:
        return reverse(f"admin:testapp_device_adminext_{name}")
    return reverse(f"admin:testapp_device_adminext_{name}", args=[pk])


class ButtonTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser("root", "root@example.invalid", "pw")
        cls.staff = User.objects.create_user("staff", "staff@example.invalid", "pw", is_staff=True)
        for codename in ("view_device", "change_device"):
            cls.staff.user_permissions.add(Permission.objects.get(codename=codename))
        cls.viewer = User.objects.create_user(
            "viewer", "viewer@example.invalid", "pw", is_staff=True
        )
        cls.viewer.user_permissions.add(Permission.objects.get(codename="view_device"))
        cls.device = Device.objects.create(name="alpha", region="eu")
        cls.other = Device.objects.create(name="beta", region="us")


class RenderingTests(ButtonTestCase):
    def test_changelist_shows_toolbar_and_row_buttons(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST)
        self.assertContains(response, "Reset all")
        self.assertContains(response, "Archive")
        self.assertContains(response, 'id="admin-ext-action-form"')

    def test_change_form_shows_object_buttons(self):
        self.client.force_login(self.superuser)
        response = self.client.get(f"{CHANGELIST}{self.device.pk}/change/")
        self.assertContains(response, "Reprocess")

    def test_add_form_has_no_object_buttons(self):
        self.client.force_login(self.superuser)
        response = self.client.get(f"{CHANGELIST}add/")
        self.assertNotContains(response, "Reprocess")

    def test_button_needing_a_permission_is_hidden(self):
        self.client.force_login(self.staff)
        response = self.client.get(CHANGELIST)
        self.assertNotContains(response, ">Purge<")

    def test_button_needing_a_permission_is_shown_when_granted(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="purge_device"))
        self.client.force_login(self.staff)
        response = self.client.get(CHANGELIST)
        self.assertContains(response, "Purge")

    def test_mutating_buttons_are_hidden_from_view_only_users(self):
        self.client.force_login(self.viewer)
        response = self.client.get(CHANGELIST)
        self.assertNotContains(response, "Reset all")
        self.assertNotContains(response, ">Archive<")
        # read_only buttons only need view permission
        self.assertContains(response, "Count devices")

    def test_label_html_is_escaped(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST)
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')
        self.assertContains(response, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;")

    def test_read_only_button_renders_a_link_not_a_submit(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST)
        html = response.content.decode()
        target = button_url("count_devices")
        self.assertIn(f'href="{target}"', html)

    def test_row_column_is_appended_once(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST)
        self.assertEqual(response.content.decode().count("admin-ext-row-buttons"), 2)


class MethodAndCsrfTests(ButtonTestCase):
    def test_get_on_a_mutating_button_is_refused(self):
        self.client.force_login(self.superuser)
        response = self.client.get(button_url("reset_all"))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Device.objects.filter(region="reset").count(), 0)

    def test_get_on_a_read_only_button_is_allowed(self):
        self.client.force_login(self.superuser)
        response = self.client.get(button_url("count_devices"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 devices.")

    def test_post_without_csrf_token_is_refused(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.superuser)
        response = client.post(button_url("reset_all"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Device.objects.filter(region="reset").count(), 0)

    def test_post_with_csrf_token_succeeds(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.superuser)
        client.get(CHANGELIST)
        token = client.cookies["csrftoken"].value
        response = client.post(button_url("reset_all"), {"csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Device.objects.filter(region="reset").count(), 2)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.post(button_url("reset_all"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
        self.assertEqual(Device.objects.filter(region="reset").count(), 0)

    def test_non_staff_user_cannot_reach_the_endpoint(self):
        User.objects.create_user("plain", "plain@example.invalid", "pw")
        self.client.login(username="plain", password="pw")
        response = self.client.post(button_url("reset_all"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Device.objects.filter(region="reset").count(), 0)


class AuthorizationTests(ButtonTestCase):
    def test_endpoint_refuses_a_missing_permission_even_when_the_url_is_guessed(self):
        self.client.force_login(self.staff)
        response = self.client.post(button_url("purge"))
        self.assertEqual(response.status_code, 403)

    def test_view_only_user_cannot_post_a_mutating_button(self):
        self.client.force_login(self.viewer)
        response = self.client.post(button_url("reset_all"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Device.objects.filter(region="reset").count(), 0)

    def test_custom_callable_cannot_widen_base_policy(self):
        """A permission callable that always returns True still cannot bypass
        the ModelAdmin's own change permission."""
        self.client.force_login(self.viewer)
        response = self.client.post(button_url("callable_permission", self.device.pk))
        self.assertEqual(response.status_code, 403)

    def test_object_outside_the_admin_queryset_is_a_404(self):
        archived = Device.objects.create(name="hidden", archived=True)
        self.client.force_login(self.superuser)
        url = reverse("restricted:testapp_device_adminext_touch", args=[archived.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_object_inside_the_admin_queryset_is_found(self):
        self.client.force_login(self.superuser)
        url = reverse("restricted:testapp_device_adminext_touch", args=[self.device.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

    def test_unknown_object_id_is_a_404(self):
        self.client.force_login(self.superuser)
        response = self.client.post(button_url("reprocess", 999999))
        self.assertEqual(response.status_code, 404)


class ScopeTests(ButtonTestCase):
    def test_changelist_button_gets_every_authorized_row(self):
        self.client.force_login(self.superuser)
        self.client.post(button_url("reset_all"))
        self.assertEqual(Device.objects.filter(region="reset").count(), 2)

    def test_filtered_button_gets_only_the_filtered_rows(self):
        self.client.force_login(self.superuser)
        url = button_url("reset_shown") + "?_changelist_filters=region%3Deu"
        self.client.post(url)
        self.device.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.device.region, "shown")
        self.assertEqual(self.other.region, "us")

    def test_filtered_button_honours_the_search_term(self):
        self.client.force_login(self.superuser)
        url = button_url("reset_shown") + "?_changelist_filters=q%3Dbeta"
        self.client.post(url)
        self.device.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.device.region, "eu")
        self.assertEqual(self.other.region, "shown")

    def test_filtered_button_without_filters_sees_everything(self):
        self.client.force_login(self.superuser)
        self.client.post(button_url("reset_shown"))
        self.assertEqual(Device.objects.filter(region="shown").count(), 2)

    def test_invalid_filters_are_rejected(self):
        self.client.force_login(self.superuser)
        url = button_url("reset_shown") + "?_changelist_filters=region__bogus%3D1"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)

    def test_object_button_acts_on_one_object(self):
        self.client.force_login(self.superuser)
        self.client.post(button_url("reprocess", self.device.pk))
        self.device.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.device.region, "reprocessed")
        self.assertEqual(self.other.region, "us")

    def test_handler_may_return_a_response(self):
        self.client.force_login(self.superuser)
        response = self.client.get(button_url("download", self.device.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"payload")


class ConfirmationTests(ButtonTestCase):
    def test_first_post_shows_a_confirmation_page_and_changes_nothing(self):
        self.client.force_login(self.superuser)
        response = self.client.post(button_url("archive", self.device.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Archive this device?")
        self.device.refresh_from_db()
        self.assertFalse(self.device.archived)

    def test_confirmed_post_runs_the_action(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            button_url("archive", self.device.pk), {"_admin_ext_confirmed": "1"}
        )
        self.assertEqual(response.status_code, 302)
        self.device.refresh_from_db()
        self.assertTrue(self.device.archived)

    def test_confirmation_page_needs_permission_too(self):
        self.client.force_login(self.viewer)
        response = self.client.post(button_url("archive", self.device.pk))
        self.assertEqual(response.status_code, 403)

    def test_confirmation_page_keeps_list_state(self):
        self.client.force_login(self.superuser)
        url = button_url("archive", self.device.pk) + "?_changelist_filters=region%3Deu"
        response = self.client.post(url)
        self.assertContains(response, "_changelist_filters=region%3Deu")


class MessageAndRedirectTests(ButtonTestCase):
    def test_message_is_shown_after_the_action(self):
        self.client.force_login(self.superuser)
        response = self.client.post(button_url("reset_all"), follow=True)
        self.assertContains(response, "Reset 2 devices.")

    def test_changelist_button_redirects_to_the_changelist_with_filters(self):
        self.client.force_login(self.superuser)
        url = button_url("reset_all") + "?_changelist_filters=region%3Deu%26o%3D2"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(CHANGELIST, response["Location"])
        self.assertIn("region=eu", response["Location"])
        self.assertIn("o=2", response["Location"])

    def test_object_button_redirects_to_the_change_page_with_filters(self):
        self.client.force_login(self.superuser)
        url = button_url("reprocess", self.device.pk) + "?_changelist_filters=region%3Deu"
        response = self.client.post(url)
        self.assertIn(f"{CHANGELIST}{self.device.pk}/change/", response["Location"])
        self.assertIn("region%3Deu", response["Location"])

    def test_row_button_redirects_to_the_changelist(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            button_url("archive", self.device.pk), {"_admin_ext_confirmed": "1"}
        )
        self.assertTrue(response["Location"].startswith(CHANGELIST))

    def test_button_urls_in_the_page_carry_the_current_list_state(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST + "?region=eu")
        self.assertContains(response, "_changelist_filters=region%3Deu")
