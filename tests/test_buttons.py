"""Buttons: rendering is a hint, the endpoint is the authority."""

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.urls import reverse

from django_extensions_admin import admin as extensions_admin

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

    def test_change_form_shows_changeform_buttons(self):
        self.client.force_login(self.superuser)
        response = self.client.get(f"{CHANGELIST}{self.device.pk}/change/")
        self.assertContains(response, "Reprocess")

    def test_add_form_has_no_object_buttons(self):
        self.client.force_login(self.superuser)
        response = self.client.get(f"{CHANGELIST}add/")
        self.assertNotContains(response, "Reprocess")

    def test_toolbar_follows_the_placement_list_not_declaration_order(self):
        """changelist_buttons = [purge, reset_all, count_devices, xss_label]."""
        self.client.force_login(self.superuser)
        html = self.client.get(CHANGELIST).content.decode()
        positions = [
            html.index(f'formaction="{button_url(name)}')
            for name in ("purge", "reset_all", "count_devices", "xss_label")
        ]
        self.assertEqual(positions, sorted(positions), "toolbar is not in placement-list order")

    def test_button_needing_a_permission_is_hidden(self):
        self.client.force_login(self.staff)
        response = self.client.get(CHANGELIST)
        self.assertNotContains(response, ">Purge<")

    def test_button_needing_a_permission_is_shown_when_granted(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="purge_device"))
        self.client.force_login(self.staff)
        response = self.client.get(CHANGELIST)
        self.assertContains(response, "Purge")

    def test_buttons_without_declared_permissions_need_change_permission(self):
        self.client.force_login(self.viewer)
        response = self.client.get(CHANGELIST)
        self.assertNotContains(response, "Reset all")
        self.assertNotContains(response, ">Archive<")
        # permissions=["view"] maps to has_view_permission, which the viewer has.
        self.assertContains(response, "Count devices")

    def test_description_html_is_escaped(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST)
        self.assertNotContains(response, '<img src=x onerror="alert(1)">')
        self.assertContains(response, "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;")

    def test_row_column_is_appended_once(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST)
        self.assertEqual(response.content.decode().count("admin-ext-row-buttons"), 2)

    def test_per_object_change_permission_hides_the_row_button(self):
        Device.objects.create(name="locked")
        self.client.force_login(self.superuser)
        html = self.client.get("/guarded/testapp/device/").content.decode()
        rows = html.split("<tr")
        locked = [row for row in rows if ">locked<" in row]
        self.assertEqual(len(locked), 1)
        self.assertNotIn("admin-ext-button--row", locked[0])
        self.assertIn("admin-ext-button--row", "".join(r for r in rows if ">alpha<" in r))


class ActionSeparationTests(ButtonTestCase):
    """Decorating or placing a button must never register a bulk action."""

    def test_buttons_are_absent_from_get_actions(self):
        model_admin = admin.site._registry[Device]
        request = self.client.request().wsgi_request
        request.user = self.superuser
        self.assertEqual(
            set(model_admin.get_actions(request)), {"delete_selected", "mark_archived"}
        )

    def test_action_dropdown_offers_only_real_actions(self):
        self.client.force_login(self.superuser)
        html = self.client.get(CHANGELIST).content.decode()
        select = html[html.index('name="action"') :]
        select = select[: select.index("</select>")]
        for name in ("reset_all", "purge", "archive", "reprocess", "count_devices"):
            self.assertNotIn(f'value="{name}"', select)
        self.assertIn('value="mark_archived"', select)


class ConfigurationErrorTests(TestCase):
    """A wrong declaration fails loudly instead of silently doing the wrong thing."""

    def build(self, **attrs):
        site = admin.AdminSite(name="throwaway")
        model_admin = type("Throwaway", (extensions_admin.ButtonsMixin, admin.ModelAdmin), attrs)
        return model_admin(Device, site)

    def test_unknown_attribute(self):
        model_admin = self.build(changelist_buttons=["nope"])
        with self.assertRaisesMessage(ImproperlyConfigured, "has no attribute 'nope'"):
            model_admin.get_urls()

    def test_undecorated_method(self):
        model_admin = self.build(changelist_buttons=["plain"], plain=lambda self, request: None)
        with self.assertRaisesMessage(ImproperlyConfigured, "not decorated with @button"):
            model_admin.get_urls()

    def test_object_handler_declared_as_a_list_button(self):
        model_admin = self.build(
            changelist_buttons=["needs_obj"],
            needs_obj=extensions_admin.button()(lambda self, request, obj: None),
        )
        with self.assertRaisesMessage(ImproperlyConfigured, "(self, request)"):
            model_admin.get_urls()

    def test_list_handler_declared_as_a_row_button(self):
        model_admin = self.build(
            row_buttons=["no_obj"],
            no_obj=extensions_admin.button()(lambda self, request: None),
        )
        with self.assertRaisesMessage(ImproperlyConfigured, "(self, request, obj)"):
            model_admin.get_urls()

    def test_same_handler_in_a_list_and_an_object_placement(self):
        model_admin = self.build(
            changelist_buttons=["both"],
            row_buttons=["both"],
            both=extensions_admin.button()(lambda self, request: None),
        )
        with self.assertRaisesMessage(ImproperlyConfigured, "cannot be both"):
            model_admin.get_urls()

    def test_unknown_permission_name(self):
        model_admin = self.build(
            changelist_buttons=["run"],
            run=extensions_admin.button(permissions=["teleport"])(lambda self, request: None),
        )
        with self.assertRaisesMessage(ImproperlyConfigured, "has_teleport_permission"):
            model_admin.get_urls()


class MethodAndCsrfTests(ButtonTestCase):
    def test_get_is_refused_on_every_button(self):
        self.client.force_login(self.superuser)
        for name, args in (
            ("reset_all", ()),
            ("count_devices", ()),
            ("reprocess", (self.device.pk,)),
            ("archive", (self.device.pk,)),
        ):
            with self.subTest(button=name):
                response = self.client.get(button_url(name, *args))
                self.assertEqual(response.status_code, 405)
        self.device.refresh_from_db()
        self.assertEqual(self.device.region, "eu")
        self.assertFalse(self.device.archived)

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

    def test_declared_permission_is_accepted_when_granted(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="purge_device"))
        self.client.force_login(self.staff)
        response = self.client.post(button_url("purge"))
        self.assertEqual(response.status_code, 302)

    def test_undeclared_button_needs_change_permission_at_the_endpoint(self):
        self.client.force_login(self.viewer)
        response = self.client.post(button_url("reset_all"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Device.objects.filter(region="reset").count(), 0)

    def test_view_permission_button_runs_for_a_view_only_user(self):
        self.client.force_login(self.viewer)
        response = self.client.post(button_url("count_devices"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 devices.")

    def test_per_object_change_permission_is_enforced_at_the_endpoint(self):
        locked = Device.objects.create(name="locked")
        self.client.force_login(self.superuser)
        denied = reverse("guarded:testapp_device_adminext_poke", args=[locked.pk])
        allowed = reverse("guarded:testapp_device_adminext_poke", args=[self.device.pk])
        self.assertEqual(self.client.post(denied).status_code, 403)
        self.assertEqual(self.client.post(allowed).status_code, 302)
        locked.refresh_from_db()
        self.assertNotEqual(locked.region, "poked")

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


class PlacementTests(ButtonTestCase):
    def test_changelist_handler_receives_only_the_request(self):
        self.client.force_login(self.superuser)
        self.client.post(button_url("reset_all"))
        self.assertEqual(Device.objects.filter(region="reset").count(), 2)

    def test_object_handler_acts_on_one_object(self):
        self.client.force_login(self.superuser)
        self.client.post(button_url("reprocess", self.device.pk))
        self.device.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(self.device.region, "reprocessed")
        self.assertEqual(self.other.region, "us")

    def test_one_handler_serves_both_object_placements_through_one_url(self):
        """`archive` is in changeform_buttons and row_buttons; there is one endpoint."""
        self.client.force_login(self.superuser)
        target = button_url("archive", self.device.pk)

        change_form = self.client.get(f"{CHANGELIST}{self.device.pk}/change/").content.decode()
        self.assertIn(f'formaction="{target}"', change_form)
        changelist = self.client.get(CHANGELIST).content.decode()
        self.assertIn(f'formaction="{target}"', changelist)

        response = self.client.post(target, {"_admin_ext_confirmed": "1"})
        self.assertEqual(response.status_code, 302)
        self.device.refresh_from_db()
        self.assertTrue(self.device.archived)

    def test_the_rendered_control_carries_where_to_return_to(self):
        self.client.force_login(self.superuser)
        change_form = self.client.get(f"{CHANGELIST}{self.device.pk}/change/").content.decode()
        self.assertIn('name="_admin_ext_return" value="changeform"', change_form)
        changelist = self.client.get(CHANGELIST).content.decode()
        self.assertIn('name="_admin_ext_return" value="changelist"', changelist)

    def test_handler_may_return_a_response(self):
        self.client.force_login(self.superuser)
        response = self.client.post(button_url("download", self.device.pk))
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

    def test_confirmation_page_keeps_list_state_and_the_return_target(self):
        self.client.force_login(self.superuser)
        url = button_url("archive", self.device.pk) + "?_changelist_filters=region%3Deu"
        response = self.client.post(url, {"_admin_ext_return": "changeform"})
        self.assertContains(response, "_changelist_filters=region%3Deu")
        self.assertContains(response, 'name="_admin_ext_return" value="changeform"')


class MessageAndRedirectTests(ButtonTestCase):
    def test_message_is_shown_after_the_action(self):
        self.client.force_login(self.superuser)
        response = self.client.post(button_url("reset_all"), follow=True)
        self.assertContains(response, "Reset 2 devices.")

    def test_handler_returning_none_gets_the_default_message(self):
        self.client.force_login(self.superuser)
        url = reverse("restricted:testapp_device_adminext_touch", args=[self.device.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Touch: done.")

    def test_changelist_button_redirects_to_the_changelist_with_filters(self):
        self.client.force_login(self.superuser)
        url = button_url("reset_all") + "?_changelist_filters=region%3Deu%26o%3D2"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(CHANGELIST, response["Location"])
        self.assertIn("region=eu", response["Location"])
        self.assertIn("o=2", response["Location"])

    def test_changeform_placement_returns_to_the_change_page(self):
        self.client.force_login(self.superuser)
        url = button_url("reprocess", self.device.pk) + "?_changelist_filters=region%3Deu"
        response = self.client.post(url, {"_admin_ext_return": "changeform"})
        self.assertIn(f"{CHANGELIST}{self.device.pk}/change/", response["Location"])
        self.assertIn("region%3Deu", response["Location"])

    def test_row_placement_returns_to_the_changelist(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            button_url("archive", self.device.pk),
            {"_admin_ext_confirmed": "1", "_admin_ext_return": "changelist"},
        )
        self.assertTrue(response["Location"].startswith(CHANGELIST))

    def test_a_missing_return_target_falls_back_to_the_changelist(self):
        self.client.force_login(self.superuser)
        response = self.client.post(button_url("reprocess", self.device.pk))
        self.assertTrue(response["Location"].startswith(CHANGELIST))
        self.assertNotIn("/change/", response["Location"])

    def test_button_urls_in_the_page_carry_the_current_list_state(self):
        self.client.force_login(self.superuser)
        response = self.client.get(CHANGELIST + "?region=eu")
        self.assertContains(response, "_changelist_filters=region%3Deu")
