"""The ModelAdmin mixin that routes, renders and guards buttons."""

from __future__ import annotations

from functools import update_wrapper

from django import forms
from django.urls import path
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .decorators import Button, collect_buttons
from .views import button_url, preserved_url, run_button

__all__ = ["AdminExtensionsMixin"]

ROW_COLUMN = "admin_ext_row_buttons"
ACTION_FORM_ID = "admin-ext-action-form"


class AdminExtensionsMixin:
    """Add to a ModelAdmin to enable ``@admin_button`` methods.

    Sets ``change_list_template`` / ``change_form_template`` to thin templates that
    extend the stock admin ones. A project that already overrides those templates
    should make its own version extend ``django_extensions_admin/change_list.html`` instead.
    """

    change_list_template = "django_extensions_admin/change_list.html"
    change_form_template = "django_extensions_admin/change_form.html"
    admin_ext_auto_row_column = True
    admin_ext_row_column_label = "Actions"

    # --- discovery -----------------------------------------------------------

    def get_admin_ext_buttons(self, request=None) -> list[Button]:
        return collect_buttons(self)

    def _buttons_for(self, scope: str, request) -> list[Button]:
        return [b for b in self.get_admin_ext_buttons(request) if b.scope == scope]

    # --- urls ----------------------------------------------------------------

    def get_urls(self):
        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        opts = self.model._meta
        prefix = f"{opts.app_label}_{opts.model_name}_adminext"
        extra = []
        for button in self.get_admin_ext_buttons():
            name = f"{prefix}_{button.name}"
            if button.scope == "changelist":
                extra.append(
                    path(
                        f"admin-ext/{button.name}/",
                        wrap(self._make_view(button)),
                        name=name,
                    )
                )
            else:
                extra.append(
                    path(
                        f"<path:object_id>/admin-ext/{button.name}/",
                        wrap(self._make_view(button)),
                        name=name,
                    )
                )
        # Before super(): the stock admin ends with a catch-all object_id route.
        return extra + super().get_urls()

    def _make_view(self, button: Button):
        def view(request, object_id=None):
            return run_button(self, button, request, object_id)

        view.__name__ = f"admin_ext_{button.name}"
        return view

    # --- rendering -----------------------------------------------------------

    @property
    def media(self):
        base = super().media
        return base + forms.Media(
            css={
                "all": [
                    "django_extensions_admin/buttons.css",
                    "django_extensions_admin/json-widget.css",
                ]
            }
        )

    def _button_context(self, button: Button, request, obj=None) -> dict:
        url = preserved_url(self, request, button_url(self, button, obj))
        return {
            "name": button.name,
            "label": button.label,
            "url": url,
            "read_only": button.read_only,
            "danger": button.danger,
            "css_class": button.css_class,
            "form_id": ACTION_FORM_ID,
        }

    def admin_ext_toolbar_buttons(self, request, scope: str, obj=None) -> list[dict]:
        return [
            self._button_context(button, request, obj)
            for button in self._buttons_for(scope, request)
            if button.is_allowed(self, request, obj)
        ]

    def changelist_view(self, request, extra_context=None):
        context = {
            "admin_ext_toolbar_buttons": self.admin_ext_toolbar_buttons(request, "changelist"),
            "admin_ext_action_form_id": ACTION_FORM_ID,
            "admin_ext_has_buttons": bool(self.get_admin_ext_buttons(request)),
            **(extra_context or {}),
        }
        return super().changelist_view(request, context)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context = dict(context)
        context["admin_ext_toolbar_buttons"] = (
            self.admin_ext_toolbar_buttons(request, "object", obj) if change and obj else []
        )
        context["admin_ext_action_form_id"] = ACTION_FORM_ID
        context["admin_ext_has_buttons"] = bool(context["admin_ext_toolbar_buttons"])
        return super().render_change_form(request, context, add, change, form_url, obj)

    # --- row column ----------------------------------------------------------

    def get_list_display(self, request):
        """Swap the row-button column for one bound to *this* request.

        The changelist renders lazily, long after this method returns, so the column has
        to carry the request itself; a ModelAdmin instance is shared between requests and
        cannot hold one.
        """
        display = list(super().get_list_display(request))
        if not self._buttons_for("row", request):
            return [item for item in display if item != ROW_COLUMN]
        column = self._row_column(request)
        if ROW_COLUMN in display:
            display[display.index(ROW_COLUMN)] = column
        elif self.admin_ext_auto_row_column:
            display.append(column)
        return display

    def _row_column(self, request):
        def admin_ext_row_buttons(obj):
            return self.render_row_buttons(request, obj)

        admin_ext_row_buttons.short_description = self.admin_ext_row_column_label
        return admin_ext_row_buttons

    def admin_ext_row_buttons(self, obj):
        """Placeholder so ``"admin_ext_row_buttons"`` can be named in list_display.

        get_list_display() replaces it with a request-bound callable; this body only
        runs if something renders the column outside a changelist.
        """
        return ""

    admin_ext_row_buttons.short_description = "Actions"

    def render_row_buttons(self, request, obj):
        """Row buttons for *obj*.

        The markup deliberately carries no ``<form>``: this cell is rendered inside the
        changelist's own form, and a nested form is invalid HTML that browsers drop.
        Each button targets the separate ``#admin-ext-action-form`` by id and overrides
        its action, which is valid HTML and leaves bulk actions and list_editable alone.
        """
        buttons = [
            self._button_context(button, request, obj)
            for button in self._buttons_for("row", request)
            if button.is_allowed(self, request, obj)
        ]
        if not buttons:
            return ""
        parts = []
        for item in buttons:
            if item["read_only"]:
                parts.append(
                    format_html(
                        '<a class="admin-ext-button admin-ext-button--row {}" href="{}">{}</a>',
                        item["css_class"],
                        item["url"],
                        item["label"],
                    )
                )
            else:
                parts.append(
                    format_html(
                        '<button type="submit" class="admin-ext-button admin-ext-button--row'
                        '{} {}" form="{}" formaction="{}" formmethod="post"'
                        ' name="_admin_ext_button" value="{}">{}</button>',
                        " admin-ext-button--danger" if item["danger"] else "",
                        item["css_class"],
                        item["form_id"],
                        item["url"],
                        item["name"],
                        item["label"],
                    )
                )
        return format_html(
            '<div class="admin-ext-row-buttons">{}</div>',
            format_html_join(mark_safe(" "), "{}", ((part,) for part in parts)),
        )
