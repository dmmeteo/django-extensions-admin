"""Our admin namespace: ``admin.button``, ``admin.ButtonsMixin``, the filters.

    from django.contrib import admin
    from django_extensions_admin import admin as extensions_admin

Import ``ModelAdmin`` and ``register`` from ``django.contrib.admin`` as usual. This is
a small namespace for this package's own API - not a proxy, mirror or monkey patch of
``django.contrib.admin``. Re-exports only, resolved on first use: Django imports every
installed app's ``admin`` module at startup, so nothing here may have side effects or
import a feature that is not installed.
"""

from importlib.util import find_spec

from . import EXPORTS, feature

NAMES = {name: EXPORTS[name] for name in EXPORTS if EXPORTS[name] in ("buttons", "filters")}

__all__ = sorted(
    n for n, f in NAMES.items() if find_spec(f"django_extensions_admin.{f}") is not None
)


def __getattr__(name: str):
    if name not in NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(feature(NAMES[name]), name)
