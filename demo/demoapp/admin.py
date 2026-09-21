"""Demo admin: every button placement and every JSON case in one place."""

from django.contrib import admin

from django_extensions_admin import admin as extensions_admin
from django_extensions_admin import readonly_json

from .models import Device, Reading


class ReadingInline(admin.TabularInline):
    """Inlines added after page load must initialise too - add a row and watch."""

    model = Reading
    extra = 1


@admin.register(Device)
class DeviceAdmin(extensions_admin.ButtonsMixin, admin.ModelAdmin):
    list_display = ("name", "region", "status", "archived")
    list_filter = ("region", "status", "archived")
    search_fields = ("name",)
    list_editable = ("status",)
    actions = ["mark_archived"]
    inlines = [ReadingInline]
    readonly_fields = ("last_report_pretty",)
    exclude = ("last_report",)

    # The lists own placement and order. `archive` appears twice on purpose: one
    # handler, one endpoint, offered both on the change form and in every row.
    changelist_buttons = ["ping_all", "count_by_region", "purge_archived"]
    changeform_buttons = ["run_diagnostics", "archive"]
    row_buttons = ["archive"]

    last_report_pretty = readonly_json("last_report", short_description="Last report")

    @admin.action(description="Mark selected devices archived")
    def mark_archived(self, request, queryset):
        queryset.update(archived=True)

    # --- the whole list: build the queryset yourself, no hidden scope ---------
    @extensions_admin.button(description="Ping all devices")
    def ping_all(self, request):
        count = self.get_queryset(request).update(status="pinged")
        return f"Pinged {count} devices."

    # --- a report: view permission is enough ---------------------------------
    @extensions_admin.button(description="Count by region", permissions=["view"])
    def count_by_region(self, request):
        from django.db.models import Count

        rows = (
            self.get_queryset(request)
            .values("region")
            .annotate(total=Count("pk"))
            .order_by("region")
        )
        summary = ", ".join(f"{row['region']}: {row['total']}" for row in rows)
        return summary or "No devices."

    # --- denied for the operator account: a permission it does not have -------
    @extensions_admin.button(
        description="Purge archived",
        permissions=["purge"],
        confirm="Delete every archived device? This cannot be undone.",
        danger=True,
    )
    def purge_archived(self, request):
        deleted, _ = self.get_queryset(request).filter(archived=True).delete()
        return (f"Purged {deleted} archived rows.", "warning")

    def has_purge_permission(self, request):
        """permissions=["purge"] looks for exactly this, like Django's actions do."""
        return request.user.has_perm("demoapp.purge_device")

    # --- one object, from the change form ------------------------------------
    @extensions_admin.button(description="Run diagnostics")
    def run_diagnostics(self, request, obj):
        obj.status = "diagnosed"
        obj.save(update_fields=["status"])
        return f"Diagnostics finished for {obj.name}."

    # --- one object, from the change form *and* from its row ------------------
    @extensions_admin.button(description="Archive", confirm=True, danger=True)
    def archive(self, request, obj):
        obj.archived = True
        obj.save(update_fields=["archived"])
        return f"Archived {obj.name}."


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    """No mixin and no widget configuration: the project-wide opt-in reaches it anyway."""

    list_display = ("__str__", "device", "label")
    list_filter = ("device",)
