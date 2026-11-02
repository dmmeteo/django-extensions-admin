"""The ``@button`` decorator and the resolved Button a placement list produces."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.utils.text import capfirst

__all__ = ["Button", "button", "resolve_buttons"]

#: Marks a ModelAdmin method as a button. Placement stays in the ModelAdmin's lists.
BUTTON_ATTR = "admin_ext_button"

#: ModelAdmin options that place buttons, and whether their handlers take an object.
PLACEMENTS = {
    "changelist_buttons": False,
    "changeform_buttons": True,
    "row_buttons": True,
}


@dataclass(frozen=True)
class ButtonOptions:
    """What the decorator records that Django has no convention for."""

    confirm: Any = None
    danger: bool = False


def button(
    *,
    description: str | None = None,
    permissions: list[str] | tuple[str, ...] | None = None,
    confirm: Any = None,
    danger: bool = False,
) -> Callable:
    """Mark a ModelAdmin method as an admin button.

    Place it with ``changelist_buttons``, ``changeform_buttons`` or ``row_buttons``;
    those lists own where a button appears and in which order. Decorating a method
    never registers a bulk action.

    description
        The label. Defaults to the method name, like Django's ``@admin.action``.
    permissions
        Names checked as ``ModelAdmin.has_<name>_permission``, exactly as
        ``@admin.action(permissions=...)``: the user needs *any* of them. Omit it and
        the button requires ``has_change_permission`` for the object in question.
    confirm
        ``True`` or a question; the handler then runs only from a confirmation page.
    danger
        Destructive styling only. It is not a permission.
    """

    def decorate(func: Callable) -> Callable:
        if description is not None:
            func.short_description = description
        if permissions is not None:
            func.allowed_permissions = permissions
        setattr(func, BUTTON_ATTR, ButtonOptions(confirm=confirm, danger=danger))
        return func

    return decorate


@dataclass(frozen=True)
class Button:
    """One button in one place: everything the mixin, template and view need."""

    name: str
    description: str
    permissions: tuple[str, ...]
    confirm: Any
    danger: bool
    takes_object: bool

    @property
    def confirm_text(self) -> str | None:
        if not self.confirm or self.confirm is True:
            return None  # the template falls back to a generic question
        return str(self.confirm)

    def is_allowed(self, model_admin, request, obj=None) -> bool:
        """The ModelAdmin's own policy decides; the button only names which part.

        Module access is always required. With no declared permissions a button is a
        change operation, checked for this object. Declared permissions follow Django's
        action rule: any one of them is enough.
        """
        if not model_admin.has_module_permission(request):
            return False
        if not self.permissions:
            return model_admin.has_change_permission(request, obj)
        return any(
            _call_permission(permission_method(model_admin, name), request, obj)
            for name in self.permissions
        )

    def default_message(self) -> str:
        return f"{self.description}: done."


def permission_method(model_admin, name: str):
    return getattr(model_admin, f"has_{name}_permission", None)


def _call_permission(method, request, obj) -> bool:
    """``has_add_permission`` takes only the request; the others also take an object."""
    takes_obj = len(inspect.signature(method).parameters) > 1
    return bool(method(request, obj) if takes_obj else method(request))


def resolve_buttons(model_admin) -> dict[str, list[Button]]:
    """Every placement list of *model_admin*, validated and in declared order.

    Called from get_urls() and from every render, so a bad declaration cannot hide.
    """
    resolved: dict[str, list[Button]] = {}
    seen: dict[str, bool] = {}
    for placement, takes_object in PLACEMENTS.items():
        buttons = []
        for name in getattr(model_admin, placement, None) or ():
            if seen.get(name, takes_object) != takes_object:
                raise ImproperlyConfigured(
                    f"{_where(model_admin, placement)} refers to {name!r}, which is already "
                    f"placed with the other handler shape. A button cannot be both a "
                    f"changelist button and an object button; use two handlers."
                )
            seen[name] = takes_object
            buttons.append(_build(model_admin, placement, name, takes_object))
        resolved[placement] = buttons
    return resolved


def _where(model_admin, placement: str) -> str:
    return f"{type(model_admin).__name__}.{placement}"


def _build(model_admin, placement: str, name: str, takes_object: bool) -> Button:
    where = _where(model_admin, placement)
    klass = type(model_admin).__name__
    handler = getattr(model_admin, name, None)
    if handler is None:
        raise ImproperlyConfigured(
            f"{where} refers to {name!r}, but {klass} has no attribute {name!r}."
        )
    if not callable(handler):
        raise ImproperlyConfigured(f"{where} refers to {name!r}, which is not callable.")
    if not isinstance(getattr(handler, BUTTON_ATTR, None), ButtonOptions):
        raise ImproperlyConfigured(
            f"{where} refers to {name!r}, which is not decorated with @button."
        )
    _check_signature(handler, where, name, takes_object)

    permissions = tuple(getattr(handler, "allowed_permissions", None) or ())
    for permission in permissions:
        if not callable(permission_method(model_admin, permission)):
            raise ImproperlyConfigured(
                f"{where} refers to {name!r}, which declares permission {permission!r}, "
                f"but {klass} has no has_{permission}_permission() method."
            )

    options = getattr(handler, BUTTON_ATTR)
    description = getattr(handler, "short_description", None)
    return Button(
        name=name,
        description=str(description) if description else capfirst(name.replace("_", " ")),
        permissions=permissions,
        confirm=options.confirm,
        danger=options.danger,
        takes_object=takes_object,
    )


def _check_signature(handler, where: str, name: str, takes_object: bool) -> None:
    """Bind placeholders rather than count parameters, so *args and defaults work."""
    arguments = (None, None) if takes_object else (None,)
    try:
        inspect.signature(handler).bind(*arguments)
    except TypeError:
        if takes_object:
            raise ImproperlyConfigured(
                f"{where} refers to {name!r}, whose handler does not accept "
                f"(self, request, obj). Change-form and row buttons are called with "
                f"the object they act on."
            ) from None
        raise ImproperlyConfigured(
            f"{where} refers to {name!r}, whose handler does not accept (self, request). "
            f"Changelist buttons get no object and no queryset; build one from "
            f"self.get_queryset(request) if you need it."
        ) from None
