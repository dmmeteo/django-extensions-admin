"""Our admin namespace: ``admin.button``, ``admin.ButtonsMixin``, the filters.

    from django.contrib import admin
    from django_extensions_admin import admin as extensions_admin

Import ``ModelAdmin`` and ``register`` from ``django.contrib.admin`` as usual. This is
a small namespace for this package's own API - not a proxy, mirror or monkey patch of
``django.contrib.admin``. Re-exports only: Django imports every installed app's
``admin`` module at startup, so nothing here may have side effects.
"""

from .buttons import ButtonsMixin, button
from .filters import (
    ChoiceFilter,
    DateRangeFilter,
    DateTimeRangeFilter,
    MultipleChoiceFilter,
    NumericRangeFilter,
)

__all__ = [
    "ButtonsMixin",
    "ChoiceFilter",
    "DateRangeFilter",
    "DateTimeRangeFilter",
    "MultipleChoiceFilter",
    "NumericRangeFilter",
    "button",
]
