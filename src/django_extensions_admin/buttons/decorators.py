"""The ``@admin_button`` decorator and the Button description it attaches."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from django.contrib import messages

__all__ = ["Button", "admin_button", "collect_buttons"]

SCOPES = ("changelist", "object", "row")

_ORDER = itertools.count()


@dataclass(frozen=True)
class Button:
    """Everything the mixin, the template and the view need to know about a button."""

    name: str
    label: str
    scope: str
    handler_name: str
    permission: Any = None
    confirm: Any = None
    danger: bool = False
    read_only: bool = False
    filtered: bool = False
    success_message: str | None = None
    css_class: str = ""
    order: int = field(default_factory=lambda: next(_ORDER))

    @property
    def method(self) -> str:
        return "get" if self.read_only else "post"

    @property
    def confirm_text(self) -> str | None:
        if not self.confirm:
            return None
        if self.confirm is True:
            return None  # the template falls back to a generic question
        return str(self.confirm)

    def is_allowed(self, model_admin, request, obj=None) -> bool:
        """Base ModelAdmin policy first, then the button's own extra check.

        ``permission=`` can only *narrow* access. A custom check that returns True can
        never hand out an action the ModelAdmin itself would refuse, so an admin that
        restricts change permission per object keeps restricting these buttons.
        """
        if not model_admin.has_module_permission(request):
            return False
        if self.read_only:
            if not model_admin.has_view_permission(request, obj):
                return False
        elif not model_admin.has_change_permission(request, obj):
            return False
        return self._extra_check(model_admin, request, obj)

    def _extra_check(self, model_admin, request, obj) -> bool:
        check = self.permission
        if check is None:
            return True
        if callable(check):
            return bool(check(request, obj))
        if isinstance(check, str):
            return request.user.has_perm(check)
        if isinstance(check, Iterable):
            return all(request.user.has_perm(perm) for perm in check)
        raise TypeError(f"Unsupported permission specification for button {self.name!r}")

    def default_message(self, model_admin) -> str:
        if self.success_message:
            return self.success_message
        return f"{self.label}: done."


def admin_button(
    label: str,
    *,
    scope: str = "object",
    name: str | None = None,
    permission: Any = None,
    confirm: Any = None,
    danger: bool = False,
    read_only: bool = False,
    filtered: bool = False,
    success_message: str | None = None,
    css_class: str = "",
) -> Callable:
    """Mark a ModelAdmin method as an admin button.

    scope
        ``"changelist"`` - one button above the list; the handler is called with
        ``(request, queryset)``.
        ``"object"`` - a button on the change form; ``(request, obj)``.
        ``"row"`` - a button in every list row; ``(request, obj)``.
    read_only
        Declares that the handler does not change data: the button renders as a link,
        GET is accepted, and view permission is enough. Mutating buttons (the default)
        are POST-only, CSRF protected and require change permission.
    filtered
        Changelist scope only: hand the handler the rows the user is currently looking
        at (the changelist filters, search and ordering) instead of every row.
    permission
        Extra requirement on top of the ModelAdmin's own policy: a permission string,
        an iterable of them, or a callable ``(request, obj)``.
    confirm
        ``True`` or a question; the action then runs only from a confirmation page.
    """
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}, got {scope!r}")
    if filtered and scope != "changelist":
        raise ValueError("filtered=True only applies to scope='changelist'")

    def decorate(func: Callable) -> Callable:
        button = Button(
            name=name or func.__name__,
            label=label,
            scope=scope,
            handler_name=func.__name__,
            permission=permission,
            confirm=confirm,
            danger=danger,
            read_only=read_only,
            filtered=filtered,
            success_message=success_message,
            css_class=css_class,
        )
        func.admin_ext_button = button
        return func

    return decorate


def collect_buttons(model_admin) -> list[Button]:
    """Every button declared on *model_admin*, in declaration order."""
    buttons: dict[str, Button] = {}
    for attr in dir(type(model_admin)):
        if attr.startswith("__"):
            continue
        member = getattr(type(model_admin), attr, None)
        button = getattr(member, "admin_ext_button", None)
        if isinstance(button, Button):
            buttons[button.name] = button
    return sorted(buttons.values(), key=lambda item: item.order)


LEVELS = {
    "debug": messages.DEBUG,
    "info": messages.INFO,
    "success": messages.SUCCESS,
    "warning": messages.WARNING,
    "error": messages.ERROR,
}
