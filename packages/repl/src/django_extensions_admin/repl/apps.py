from django.apps import AppConfig


class ReplConfig(AppConfig):
    name = "django_extensions_admin.repl"
    label = "admin_ext_repl"
    verbose_name = "Admin REPL"

    def ready(self) -> None:
        from django.core import checks

        from ..panel import Tool, register
        from .checks import check_repl
        from .tool import available, context

        checks.register(check_repl)
        register(
            Tool(
                key="repl",
                label="Django shell",
                template="django_extensions_admin/repl/tool.html",
                available=available,
                context=context,
                css=("django_extensions_admin/repl/repl.css",),
                js_modules=("django_extensions_admin/repl/repl.js",),
            )
        )
