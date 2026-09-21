"""The ModelAdmin mixin that routes, renders and guards buttons."""

from __future__ import annotations

from functools import update_wrapper

from django import forms
from django.urls import path
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .decorators import Button, resolve_buttons
from .views import RETURN_CHANGEFORM, RETURN_CHANGELIST, button_url, preserved_url, run_button

__all__ = ["ButtonsMixin"]

ROW_BUTTONS_COLUMN = "row_buttons_column"
ACTION_FORM_ID = "admin-ext-action-form"


class ButtonsMixin:
    """Add to a ModelAdmin to place ``@button`` methods in the stock admin.

    Three lists own placement and order: ``changelist_buttons`` above the list,
    ``changeform_buttons`` on an existing object's change form, ``row_buttons`` in every
    list row. The same object handler may appear in both object lists. None of this
    touches ``ModelAdmin.actions``.

    Sets ``change_list_template`` / ``change_form_template`` to thin templates that
    extend the stock admin ones. A project that already overrides those templates should
    make its own version extend ``django_extensions_admin/change_list.html`` instead.
    """

    change_list_template = "django_extensions_admin/change_list.html"
    change_form_template = "django_extensions_admin/change_form.html"

    changelist_buttons: list[str] = []
    changeform_buttons: list[str] = []
    row_buttons: list[str] = []

    auto_row_buttons_column = True
    row_buttons_column_label = "Actions"

    # --- placement -----------------------------------------------------------

    def get_buttons(self) -> dict[str, list[Button]]:
        """Every placement list, validated. Raises ImproperlyConfigured on a bad name."""
        return resolve_buttons(self)

    def _placed(self, placement: str) -> list[Button]:
        return self.get_buttons()[placement]

    # --- urls ----------------------------------------------------------------

    def get_urls(self):
        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        opts = self.model._meta
        prefix = f"{opts.app_label}_{opts.model_name}_adminext"
        # One route per handler, not per placement: a button placed on both the change
        # form and the rows is still a single endpoint.
        routes: dict[str, Button] = {}
        for buttons in self.get_buttons().values():
            for button in buttons:
                routes.setdefault(button.name, button)

        extra = []
        for button in routes.values():
            route = (
                f"<path:object_id>/admin-ext/{button.name}/"
                if button.takes_object
                else (f"admin-ext/{button.name}/")
            )
            extra.append(path(route, wrap(self._make_view(button)), name=f"{prefix}_{button.name}"))
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
        return super().media + forms.Media(css={"all": ["django_extensions_admin/buttons.css"]})

    def _button_context(self, button: Button, request, obj=None, *, return_to) -> dict:
        return {
            "name": button.name,
            "label": button.description,
            "url": preserved_url(self, request, button_url(self, button, obj)),
            "danger": button.danger,
            "form_id": ACTION_FORM_ID,
            "return_to": return_to,
        }

    def get_toolbar_buttons(self, request, placement: str, obj=None) -> list[dict]:
        return_to = RETURN_CHANGEFORM if placement == "changeform_buttons" else RETURN_CHANGELIST
        return [
            self._button_context(button, request, obj, return_to=return_to)
            for button in self._placed(placement)
            if button.is_allowed(self, request, obj)
        ]

    def changelist_view(self, request, extra_context=None):
        buttons = self.get_buttons()
        context = {
            "admin_ext_toolbar_buttons": self.get_toolbar_buttons(request, "changelist_buttons"),
            "admin_ext_action_form_id": ACTION_FORM_ID,
            "admin_ext_has_buttons": any(buttons.values()),
            **(extra_context or {}),
        }
        return super().changelist_view(request, context)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context = dict(context)
        context["admin_ext_toolbar_buttons"] = (
            self.get_toolbar_buttons(request, "changeform_buttons", obj) if change and obj else []
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
        buttons = self._placed("row_buttons")
        if not buttons:
            return [item for item in display if item != ROW_BUTTONS_COLUMN]
        column = self._row_column(request, buttons)
        if ROW_BUTTONS_COLUMN in display:
            display[display.index(ROW_BUTTONS_COLUMN)] = column
        elif self.auto_row_buttons_column:
            display.append(column)
        return display

    def _row_column(self, request, buttons):
        # The placement lists do not vary per row, so resolve them once for the page.
        def row_buttons_column(obj):
            return self.render_row_buttons(request, obj, buttons)

        row_buttons_column.short_description = self.row_buttons_column_label
        return row_buttons_column

    def row_buttons_column(self, obj):
        """Placeholder so ``"row_buttons_column"`` can be named in list_display.

        get_list_display() replaces it with a request-bound callable; this body only
        runs if something renders the column outside a changelist.
        """
        return ""

    row_buttons_column.short_description = "Actions"

    def render_row_buttons(self, request, obj, buttons=None):
        """Row buttons for *obj*.

        The markup deliberately carries no ``<form>``: this cell is rendered inside the
        changelist's own form, and a nested form is invalid HTML that browsers drop.
        Each button targets the separate ``#admin-ext-action-form`` by id and overrides
        its action, which is valid HTML and leaves bulk actions and list_editable alone.
        """
        if buttons is None:
            buttons = self._placed("row_buttons")
        items = [
            self._button_context(button, request, obj, return_to=RETURN_CHANGELIST)
            for button in buttons
            if button.is_allowed(self, request, obj)
        ]
        if not items:
            return ""
        parts = [
            format_html(
                '<button type="submit" class="admin-ext-button admin-ext-button--row{}"'
                ' form="{}" formaction="{}" formmethod="post"'
                ' name="_admin_ext_return" value="{}">{}</button>',
                " admin-ext-button--danger" if item["danger"] else "",
                item["form_id"],
                item["url"],
                item["return_to"],
                item["label"],
            )
            for item in items
        ]
        return format_html(
            '<div class="admin-ext-row-buttons">{}</div>',
            format_html_join(mark_safe(" "), "{}", ((part,) for part in parts)),
        )
