"""django-extensions-admin: small, native-looking additions to django.contrib.admin."""

from .buttons import ButtonsMixin, button
from .jsonwidget import JSONReadonlyMixin, PrettyJSONWidget, readonly_json, render_json

__all__ = [
    "ButtonsMixin",
    "JSONReadonlyMixin",
    "PrettyJSONWidget",
    "button",
    "readonly_json",
    "render_json",
]

__version__ = "0.1.0"
