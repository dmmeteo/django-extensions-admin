"""App config, and the optional project-wide JSON widget default."""

from __future__ import annotations

from django.apps import AppConfig

__all__ = ["AdminExtensionsConfig", "install_json_widget_default"]


class AdminExtensionsConfig(AppConfig):
    name = "django_extensions_admin"
    label = "django_extensions_admin"
    verbose_name = "Django admin kit"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from .conf import get_setting

        if get_setting("JSON_WIDGET_DEFAULT"):
            install_json_widget_default()


def declares_own_json_widget(model_admin) -> bool:
    """True when the ModelAdmin class itself asks for a JSONField widget.

    Looked up on the classes rather than the instance, because ModelAdmin.__init__ has
    already merged FORMFIELD_FOR_DBFIELD_DEFAULTS into the instance attribute.
    """
    from django.db import models

    for klass in type(model_admin).__mro__:
        overrides = klass.__dict__.get("formfield_overrides")
        if overrides and "widget" in overrides.get(models.JSONField, {}):
            return True
    return False


def install_json_widget_default():
    """Make PrettyJSONWidget the admin-wide default for models.JSONField.

    Two steps, because app order is not guaranteed: set the default that ModelAdmin
    reads at construction time, and back-fill any admin that was already built (which
    happens when django.contrib.admin's autodiscovery ran before this app's ready()).
    An explicit per-ModelAdmin override always wins.
    """
    from django.contrib.admin.options import FORMFIELD_FOR_DBFIELD_DEFAULTS
    from django.db import models

    from .jsonwidget.widgets import PrettyJSONWidget

    FORMFIELD_FOR_DBFIELD_DEFAULTS.setdefault(models.JSONField, {})
    FORMFIELD_FOR_DBFIELD_DEFAULTS[models.JSONField]["widget"] = PrettyJSONWidget

    for site in _known_sites():
        for model_admin in list(site._registry.values()):
            _backfill(model_admin)
            for inline_class in getattr(model_admin, "inlines", ()):
                _backfill(inline_class(model_admin.model, site))


def _backfill(model_admin):
    from django.db import models

    from .jsonwidget.widgets import PrettyJSONWidget

    if declares_own_json_widget(model_admin):
        return
    overrides = dict(getattr(model_admin, "formfield_overrides", {}) or {})
    entry = dict(overrides.get(models.JSONField, {}))
    entry["widget"] = PrettyJSONWidget
    overrides[models.JSONField] = entry
    model_admin.formfield_overrides = overrides
    # Inline instances are rebuilt per request from the class, so the class needs it too.
    type(model_admin).formfield_overrides = overrides


def _known_sites():
    from django.contrib import admin

    sites = [admin.site]
    try:
        from django.contrib.admin.sites import all_sites
    except ImportError:  # pragma: no cover - very old Django
        return sites
    for site in all_sites:
        if site not in sites:
            sites.append(site)
    return sites
