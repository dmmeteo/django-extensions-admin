"""Demo admin: every button scope and every JSON case in one place."""

from django.contrib import admin

from django_extensions_admin import AdminExtensionsMixin, admin_button, readonly_json

from .models import Device, Reading


class ReadingInline(admin.TabularInline):
    """Inlines added after page load must initialise too - add a row and watch."""

    model = Reading
    extra = 1


@admin.register(Device)
class DeviceAdmin(AdminExtensionsMixin, admin.ModelAdmin):
    list_display = ("name", "region", "status", "archived")
    list_filter = ("region", "status", "archived")
    search_fields = ("name",)
    list_editable = ("status",)
    actions = ["mark_archived"]
    inlines = [ReadingInline]
    readonly_fields = ("last_report_pretty",)
    exclude = ("last_report",)

    last_report_pretty = readonly_json("last_report", short_description="Last report")

    @admin.action(description="Mark selected devices archived")
    def mark_archived(self, request, queryset):
        queryset.update(archived=True)

    # --- global: every device the current user may change --------------------
    @admin_button("Ping all devices", scope="changelist")
    def ping_all(self, request, queryset):
        count = queryset.update(status="pinged")
        return f"Pinged {count} devices."

    # --- global, but only what the list is currently showing ------------------
    @admin_button("Ping shown devices", scope="changelist", filtered=True)
    def ping_shown(self, request, queryset):
        count = queryset.update(status="pinged")
        return f"Pinged {count} devices matching the current filters."

    # --- read-only: a link, GET is fine, view permission is enough ------------
    @admin_button("Count by region", scope="changelist", read_only=True)
    def count_by_region(self, request, queryset):
        from django.db.models import Count

        rows = queryset.values("region").annotate(total=Count("pk")).order_by("region")
        summary = ", ".join(f"{row['region']}: {row['total']}" for row in rows)
        return summary or "No devices."

    # --- denied for the operator account: permission it does not have ---------
    @admin_button(
        "Purge archived",
        scope="changelist",
        permission="demoapp.purge_device",
        confirm="Delete every archived device? This cannot be undone.",
        danger=True,
    )
    def purge_archived(self, request, queryset):
        deleted, _ = queryset.filter(archived=True).delete()
        return (f"Purged {deleted} archived rows.", "warning")

    # --- one object, from the change form ------------------------------------
    @admin_button("Run diagnostics", scope="object")
    def run_diagnostics(self, request, obj):
        obj.status = "diagnosed"
        obj.save(update_fields=["status"])
        return f"Diagnostics finished for {obj.name}."

    # --- one object, from its row in the list ---------------------------------
    @admin_button("Archive", scope="row", confirm=True, danger=True)
    def archive(self, request, obj):
        obj.archived = True
        obj.save(update_fields=["archived"])
        return f"Archived {obj.name}."


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    """No mixin and no widget configuration: the project-wide opt-in reaches it anyway."""

    list_display = ("__str__", "device", "label")
    list_filter = ("device",)
