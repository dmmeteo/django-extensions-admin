"""App config: the startup hooks of the features that have one, when installed and asked for."""

from __future__ import annotations

from importlib.util import find_spec

from django.apps import AppConfig, apps
from django.core import checks

__all__ = ["AdminExtensionsConfig", "check_feature_settings"]

# Which feature reads each ADMIN_EXTENSIONS key, by prefix. A key for a feature that is not
# installed changes nothing; check_feature_settings says so instead of failing.
SETTING_FEATURES = {
    "JSON_": "jsonwidget",
    "COMMANDS_": "commands",
    "BRANDING": "branding",
    "ENVIRONMENT": "environment",
    "PANEL_": "panel",
    "REPL_": "repl",
}
# Features that are Django apps of their own: installing the distribution is not enough.
APP_FEATURES = ("environment", "panel", "repl")


class AdminExtensionsConfig(AppConfig):
    name = "django_extensions_admin"
    label = "django_extensions_admin"
    verbose_name = "Django admin extensions"
    default_auto_field = "django.db.models.AutoField"

    def ready(self):
        from .conf import get_setting

        if get_setting("JSON_WIDGET_DEFAULT") and installed("jsonwidget"):
            from .jsonwidget.default import install_json_widget_default

            install_json_widget_default()
        # Silent unless ADMIN_EXTENSIONS["BRANDING"] is configured.
        if installed("branding"):
            from .branding import check_branding

            checks.register(check_branding)
        checks.register(check_feature_settings)


def installed(feature: str) -> bool:
    return find_spec(f"django_extensions_admin.{feature}") is not None


def check_feature_settings(app_configs=None, **kwargs):
    """Warn about settings whose feature is not installed or not in INSTALLED_APPS."""
    from django.conf import settings

    configured = getattr(settings, "ADMIN_EXTENSIONS", None) or {}
    warnings = []
    for key in sorted(configured):
        feature = next((f for p, f in SETTING_FEATURES.items() if key.startswith(p)), None)
        if feature is None or configured[key] in (None, "", False):
            continue
        obj = f"ADMIN_EXTENSIONS[{key!r}]"
        if not installed(feature):
            warnings.append(
                checks.Warning(
                    f"{obj} is set, but the {feature} feature is not installed: it does nothing.",
                    hint=f'pip install "django-extensions-admin[{feature}]", or drop the setting.',
                    obj=obj,
                    id="django_extensions_admin.W001",
                )
            )
        elif feature in APP_FEATURES and not apps.is_installed(
            f"django_extensions_admin.{feature}"
        ):
            warnings.append(
                checks.Warning(
                    f"{obj} is set, but django_extensions_admin.{feature} is not in INSTALLED_APPS,"
                    " so it does nothing.",
                    hint=f'Add "django_extensions_admin.{feature}" to INSTALLED_APPS.',
                    obj=obj,
                    id="django_extensions_admin.W002",
                )
            )
    return warnings
