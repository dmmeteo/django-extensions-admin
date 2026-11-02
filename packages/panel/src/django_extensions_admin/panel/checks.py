from django.core import checks

SIDES = ("right", "left")


def side() -> str:
    from ..conf import get_setting

    value = get_setting("PANEL_SIDE")
    return value if value in SIDES else "right"


def check_panel(app_configs=None, **kwargs):
    from ..conf import get_setting

    value = get_setting("PANEL_SIDE")
    if value in SIDES:
        return []
    return [
        checks.Error(
            f"ADMIN_EXTENSIONS['PANEL_SIDE'] is {value!r}; use 'right' or 'left'.",
            hint="The panel docks to the right until this is fixed.",
            obj="ADMIN_EXTENSIONS['PANEL_SIDE']",
            id="django_extensions_admin.E401",
        )
    ]
