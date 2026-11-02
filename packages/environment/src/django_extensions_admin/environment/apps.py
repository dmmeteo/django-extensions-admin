from django.apps import AppConfig
from django.core import checks


class EnvironmentConfig(AppConfig):
    name = "django_extensions_admin.environment"
    label = "admin_ext_environment"
    verbose_name = "Admin environment indicator"

    def ready(self):
        from .indicator import check_environment

        checks.register(check_environment)
