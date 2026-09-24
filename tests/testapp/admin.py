"""Admins used by the test suite; each one exercises a documented pattern."""

from django.contrib import admin
from django.db import models

from django_extensions_admin import (
    ChoiceFilter,
    DateRangeFilter,
    DateTimeRangeFilter,
    JSONReadonlyMixin,
    MultipleChoiceFilter,
    NumericRangeFilter,
    PrettyJSONWidget,
    readonly_json,
)
from django_extensions_admin import admin as extensions_admin

from .models import Device, Reading


class ReadingInline(admin.TabularInline):
    model = Reading
    extra = 1


@admin.register(Device)
class DeviceAdmin(extensions_admin.ButtonsMixin, admin.ModelAdmin):
    list_display = ("name", "region", "archived")
    list_editable = ("region",)
    list_filter = ("region", "archived")
    search_fields = ("name",)
    actions = ["mark_archived"]
    inlines = [ReadingInline]
    readonly_fields = ("notes_pretty",)
    formfield_overrides = {models.JSONField: {"widget": PrettyJSONWidget}}

    # Declaration order below is deliberately not toolbar order: the lists own placement
    # and order, and "Purge" is declared last but rendered first.
    changelist_buttons = ["purge", "reset_all", "count_devices", "xss_label"]
    changeform_buttons = ["reprocess", "download", "archive"]
    row_buttons = ["archive"]

    notes_pretty = readonly_json("notes", short_description="Notes (read only)")

    @admin.action(description="Mark archived")
    def mark_archived(self, request, queryset):
        queryset.update(archived=True)

    @extensions_admin.button(description="Reset all")
    def reset_all(self, request):
        count = self.get_queryset(request).update(region="reset")
        return f"Reset {count} devices."

    @extensions_admin.button(description="Count devices", permissions=["view"])
    def count_devices(self, request):
        return f"{self.get_queryset(request).count()} devices."

    @extensions_admin.button(description="Purge", permissions=["purge"], danger=True)
    def purge(self, request):
        return "purged"

    @extensions_admin.button(description='<img src=x onerror="alert(1)">')
    def xss_label(self, request):
        return "ok"

    @extensions_admin.button(description="Reprocess")
    def reprocess(self, request, obj):
        obj.region = "reprocessed"
        obj.save(update_fields=["region"])
        return f"Reprocessed {obj.name}."

    @extensions_admin.button(description="Archive", confirm="Archive this device?")
    def archive(self, request, obj):
        obj.archived = True
        obj.save(update_fields=["archived"])
        return f"Archived {obj.name}."

    @extensions_admin.button(description="Download")
    def download(self, request, obj):
        from django.http import HttpResponse

        return HttpResponse(b"payload", content_type="text/plain")

    def has_purge_permission(self, request):
        """The Django-action idiom: permissions=["purge"] looks for exactly this."""
        return request.user.has_perm("testapp.purge_device")


class VisibleDeviceAdmin(extensions_admin.ButtonsMixin, admin.ModelAdmin):
    """Second admin site registration: only non-archived devices are visible at all."""

    changeform_buttons = ["touch"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(archived=False)

    @extensions_admin.button(description="Touch")
    def touch(self, request, obj):
        """Returns nothing: the view supplies the default message."""


class GuardedDeviceAdmin(extensions_admin.ButtonsMixin, admin.ModelAdmin):
    """Per-object change permission: the button follows it, at render and at the endpoint."""

    list_display = ("name", "region")
    row_buttons = ["poke"]

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.name == "locked":
            return False
        return super().has_change_permission(request, obj)

    @extensions_admin.button(description="Poke")
    def poke(self, request, obj):
        obj.region = "poked"
        obj.save(update_fields=["region"])
        return "poked"


restricted_site = admin.AdminSite(name="restricted")
restricted_site.register(Device, VisibleDeviceAdmin)

guarded_site = admin.AdminSite(name="guarded")
guarded_site.register(Device, GuardedDeviceAdmin)


class PlainReadingAdmin(admin.ModelAdmin):
    """No mixin and no widget override: the project-wide JSON opt-in and the range filters.

    Range filters are plain ``list_filter`` entries, so this admin needs nothing else -
    not the buttons mixin, not a custom template, not a setting.
    """

    list_display = ("id", "device", "recorded_on", "recorded_at", "value", "sequence")
    list_filter = (
        ("recorded_on", DateRangeFilter),
        ("recorded_at", DateRangeFilter),
        ("value", NumericRangeFilter),
        ("sequence", NumericRangeFilter),
        "device__region",
    )
    search_fields = ("device__name",)


admin.site.register(Reading, PlainReadingAdmin)


class InstantReadingAdmin(admin.ModelAdmin):
    """The same field, filtered to the minute instead of to the day."""

    list_filter = (("recorded_at", DateTimeRangeFilter),)


instant_site = admin.AdminSite(name="instant")
instant_site.register(Reading, InstantReadingAdmin)


class RecentReadingAdmin(admin.ModelAdmin):
    """An admin that hides rows: the range filter may only narrow what this returns."""

    list_filter = (("value", NumericRangeFilter),)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(sequence__gte=3)


recent_site = admin.AdminSite(name="recent")
recent_site.register(Reading, RecentReadingAdmin)


class ReadonlyOnlyDeviceAdmin(JSONReadonlyMixin, admin.ModelAdmin):
    """JSON rendered read-only and nothing else: no editable widget, no buttons mixin.

    The mixin is the whole opt-in; without it the page would still be readable, just
    unstyled. `fields` keeps every editable JSONField off the page on purpose.
    """

    fields = ("name", "notes_pretty")
    readonly_fields = ("notes_pretty",)

    notes_pretty = readonly_json("notes", short_description="Notes (read only)")


class UnstyledReadonlyReadingAdmin(admin.ModelAdmin):
    """The same rendering without the mixin: readable text, no stylesheet."""

    fields = ("device", "payload_pretty")
    readonly_fields = ("payload_pretty",)

    payload_pretty = readonly_json("payload", short_description="Payload (read only)")


readonly_site = admin.AdminSite(name="readonly")
readonly_site.register(Device, ReadonlyOnlyDeviceAdmin)
readonly_site.register(Reading, UnstyledReadonlyReadingAdmin)


class SearchableTagFilter(MultipleChoiceFilter):
    """The search box normally waits for a long list; this one asks for it early."""

    search_threshold = 2


class ChoiceDeviceAdmin(admin.ModelAdmin):
    """Choice filters over a choices field, an M2M and a plain column.

    Archived devices are not part of this admin at all, so no filter may bring them back.
    """

    list_display = ("name", "region", "kind")
    list_filter = (
        ("kind", ChoiceFilter),
        ("tags", SearchableTagFilter),
        ("region", MultipleChoiceFilter),
    )
    search_fields = ("name",)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(archived=False)


class ChoiceReadingAdmin(admin.ModelAdmin):
    """A single choice over a foreign key, multiple choices over a nullable one, through a
    relation and over an integer - which also carries a range filter of its own."""

    list_display = ("sequence", "device", "tag")
    list_filter = (
        ("device", ChoiceFilter),
        ("tag", MultipleChoiceFilter),
        ("device__region", MultipleChoiceFilter),
        ("sequence", MultipleChoiceFilter),
        ("sequence", NumericRangeFilter),
        "device__archived",
    )
    search_fields = ("device__name",)
    list_per_page = 2


choices_site = admin.AdminSite(name="choices")
choices_site.register(Device, ChoiceDeviceAdmin)
choices_site.register(Reading, ChoiceReadingAdmin)
