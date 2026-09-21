"""Project-wide opt-in: it must reach admins that never heard of the library, and it
must never overrule an admin that asked for something else."""

from django.contrib import admin
from django.contrib.admin.options import FORMFIELD_FOR_DBFIELD_DEFAULTS
from django.db import models
from django.forms import Textarea
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from django_extensions_admin import PrettyJSONWidget
from django_extensions_admin.apps import declares_own_json_widget, install_json_widget_default

from .testapp.admin import DeviceAdmin
from .testapp.models import Device, Reading


class OptInDefaultTests(TestCase):
    def setUp(self):
        self.previous = FORMFIELD_FOR_DBFIELD_DEFAULTS.get(models.JSONField, {}).copy()
        self.reading_admin = admin.site._registry[Reading]
        self.reading_overrides = self.reading_admin.formfield_overrides
        self.reading_class_overrides = type(self.reading_admin).__dict__.get("formfield_overrides")
        self.addCleanup(self.restore)

    def restore(self):
        if self.previous:
            FORMFIELD_FOR_DBFIELD_DEFAULTS[models.JSONField] = self.previous
        else:
            FORMFIELD_FOR_DBFIELD_DEFAULTS.pop(models.JSONField, None)
        self.reading_admin.formfield_overrides = self.reading_overrides
        if self.reading_class_overrides is None:
            try:
                del type(self.reading_admin).formfield_overrides
            except AttributeError:
                pass
        else:
            type(self.reading_admin).formfield_overrides = self.reading_class_overrides

    def test_off_by_default(self):
        widget = FORMFIELD_FOR_DBFIELD_DEFAULTS.get(models.JSONField, {}).get("widget")
        self.assertIsNot(widget, PrettyJSONWidget)

    def test_install_sets_the_admin_wide_default(self):
        install_json_widget_default()
        self.assertIs(FORMFIELD_FOR_DBFIELD_DEFAULTS[models.JSONField]["widget"], PrettyJSONWidget)

    def test_install_backfills_an_already_registered_admin(self):
        """Covers the case where admin autodiscovery ran before this app's ready()."""
        install_json_widget_default()
        request = RequestFactory().get("/")
        form_field = self.reading_admin.formfield_for_dbfield(
            Reading._meta.get_field("payload"), request=request
        )
        self.assertIsInstance(form_field.widget, PrettyJSONWidget)

    def test_install_does_not_override_an_explicit_choice(self):
        class OpinionatedAdmin(admin.ModelAdmin):
            formfield_overrides = {models.JSONField: {"widget": Textarea}}

        model_admin = OpinionatedAdmin(Device, admin.site)
        self.assertTrue(declares_own_json_widget(model_admin))
        install_json_widget_default()
        request = RequestFactory().get("/")
        form_field = model_admin.formfield_for_dbfield(
            Device._meta.get_field("config"), request=request
        )
        self.assertNotIsInstance(form_field.widget, PrettyJSONWidget)
        self.assertIsInstance(form_field.widget, Textarea)

    def test_an_admin_built_after_install_picks_the_default_up(self):
        install_json_widget_default()

        class LateAdmin(admin.ModelAdmin):
            pass

        model_admin = LateAdmin(Device, admin.site)
        form_field = model_admin.formfield_for_dbfield(
            Device._meta.get_field("config"), request=RequestFactory().get("/")
        )
        self.assertIsInstance(form_field.widget, PrettyJSONWidget)


class ExplicitOverrideTests(SimpleTestCase):
    def test_declared_widget_is_detected_through_the_mro(self):
        self.assertTrue(declares_own_json_widget(DeviceAdmin(Device, admin.site)))


class SettingsTests(SimpleTestCase):
    def test_settings_defaults(self):
        from django_extensions_admin.conf import get_setting

        self.assertFalse(get_setting("JSON_WIDGET_DEFAULT"))
        self.assertEqual(get_setting("JSON_INDENT"), 2)

    @override_settings(ADMIN_EXTENSIONS={"JSON_INDENT": 4})
    def test_setting_is_read_from_the_project(self):
        from django_extensions_admin.conf import get_setting

        self.assertEqual(get_setting("JSON_INDENT"), 4)

    def test_unknown_setting_is_refused(self):
        from django_extensions_admin.conf import get_setting

        with self.assertRaises(KeyError):
            get_setting("NOPE")
