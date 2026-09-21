"""Admins used by the test suite; each one exercises a documented pattern."""

from django.contrib import admin
from django.db import models

from django_extensions_admin import (
    AdminExtensionsMixin,
    PrettyJSONWidget,
    admin_button,
    readonly_json,
)

from .models import Device, Reading


class ReadingInline(admin.TabularInline):
    model = Reading
    extra = 1


@admin.register(Device)
class DeviceAdmin(AdminExtensionsMixin, admin.ModelAdmin):
    list_display = ("name", "region", "archived")
    list_editable = ("region",)
    list_filter = ("region", "archived")
    search_fields = ("name",)
    actions = ["mark_archived"]
    inlines = [ReadingInline]
    readonly_fields = ("notes_pretty",)
    formfield_overrides = {models.JSONField: {"widget": PrettyJSONWidget}}

    notes_pretty = readonly_json("notes", short_description="Notes (read only)")

    @admin.action(description="Mark archived")
    def mark_archived(self, request, queryset):
        queryset.update(archived=True)

    @admin_button("Reset all", scope="changelist")
    def reset_all(self, request, queryset):
        count = queryset.update(region="reset")
        return f"Reset {count} devices."

    @admin_button("Reset shown", scope="changelist", filtered=True)
    def reset_shown(self, request, queryset):
        count = queryset.update(region="shown")
        return f"Reset {count} shown devices."

    @admin_button("Count devices", scope="changelist", read_only=True)
    def count_devices(self, request, queryset):
        return f"{queryset.count()} devices."

    @admin_button("Purge", scope="changelist", permission="testapp.purge_device", danger=True)
    def purge(self, request, queryset):
        return "purged"

    @admin_button("Reprocess", scope="object")
    def reprocess(self, request, obj):
        obj.region = "reprocessed"
        obj.save(update_fields=["region"])
        return f"Reprocessed {obj.name}."

    @admin_button("Archive", scope="row", confirm="Archive this device?")
    def archive(self, request, obj):
        obj.archived = True
        obj.save(update_fields=["archived"])
        return f"Archived {obj.name}."

    @admin_button('<img src=x onerror="alert(1)">', scope="row", name="xss_label")
    def xss_label(self, request, obj):
        return "ok"

    @admin_button(
        "Always allowed by callable", scope="object", permission=lambda request, obj: True
    )
    def callable_permission(self, request, obj):
        return "ran"

    @admin_button("Download", scope="object", read_only=True, name="download")
    def download(self, request, obj):
        from django.http import HttpResponse

        return HttpResponse(b"payload", content_type="text/plain")


class VisibleDeviceAdmin(AdminExtensionsMixin, admin.ModelAdmin):
    """Second admin site registration: only non-archived devices are visible at all."""

    def get_queryset(self, request):
        return super().get_queryset(request).filter(archived=False)

    @admin_button("Touch", scope="object", name="touch")
    def touch(self, request, obj):
        return "touched"


restricted_site = admin.AdminSite(name="restricted")
restricted_site.register(Device, VisibleDeviceAdmin)


class PlainReadingAdmin(admin.ModelAdmin):
    """No mixin, no widget override: used for the project-wide opt-in tests."""


admin.site.register(Reading, PlainReadingAdmin)
