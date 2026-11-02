from django.apps import AppConfig
from django.core import checks


class PanelConfig(AppConfig):
    name = "django_extensions_admin.panel"
    label = "admin_ext_panel"
    verbose_name = "Admin tools panel"

    def ready(self):
        from .checks import check_panel

        checks.register(check_panel)
