"""django-extensions-admin: small, native-looking additions to django.contrib.admin."""

from .buttons import AdminExtensionsMixin, admin_button
from .jsonwidget import PrettyJSONWidget, readonly_json, render_json

__all__ = [
    "AdminExtensionsMixin",
    "PrettyJSONWidget",
    "admin_button",
    "readonly_json",
    "render_json",
]

__version__ = "0.1.0"
