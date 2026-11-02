"""django-extensions-admin: small, native-looking additions to django.contrib.admin.

Each feature is a separate distribution installed into this package by an extra, such as
``pip install "django-extensions-admin[buttons,jsonwidget]"``. The names below resolve on
first use, so importing this package imports no feature, and a name whose feature is not
installed says which extra provides it.
"""

from importlib import import_module
from importlib.util import find_spec

__version__ = "0.1.0"

# Public name -> the feature subpackage (and extra) that provides it.
EXPORTS = {
    "ButtonsMixin": "buttons",
    "button": "buttons",
    "ChoiceFilter": "filters",
    "DateRangeFilter": "filters",
    "DateTimeRangeFilter": "filters",
    "MultipleChoiceFilter": "filters",
    "NumericRangeFilter": "filters",
    "JSONReadonlyMixin": "jsonwidget",
    "PrettyJSONWidget": "jsonwidget",
    "readonly_json": "jsonwidget",
    "render_json": "jsonwidget",
}

# Only installed features' names, so a star import works on any selection.
__all__ = sorted(name for name, f in EXPORTS.items() if find_spec(f"{__name__}.{f}") is not None)


def feature(name: str):
    """Import an installed feature subpackage, or explain which extra is missing."""
    module = f"{__name__}.{name}"
    try:
        return import_module(module)
    except ModuleNotFoundError as error:
        if error.name != module:
            raise
        raise ImportError(
            f"{module} is not installed. Install it with: "
            f'pip install "django-extensions-admin[{name}]"',
            name=module,
        ) from None


def __getattr__(name: str):
    if name not in EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(feature(EXPORTS[name]), name)
