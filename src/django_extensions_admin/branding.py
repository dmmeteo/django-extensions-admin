"""Optional branding: one logo and a few of the admin's own colour variables.

Adopted by a project template, ``admin/base_site.html``, that extends
``django_extensions_admin/branding/base_site.html``; the values come from
``ADMIN_EXTENSIONS["BRANDING"]``. Nothing here runs until that template renders, and the
setting alone changes nothing.

Colours are Django's documented admin CSS variables, limited to the brand surfaces -
header, breadcrumbs, module captions, links and buttons - and never the body, borders,
messages or fonts. Values are hex only, so what reaches the page is a fixed variable name
and a validated colour, never CSS of the project's own.
"""

from __future__ import annotations

import re
from typing import Any

from django.core import checks

__all__ = ["DARK_SENSITIVE", "PALETTE", "check_branding", "resolve"]

# Every variable a project may set. Each is defined by Django's admin/css/base.css.
PALETTE = frozenset(
    {
        "primary",
        "secondary",
        "accent",
        "header-bg",
        "header-color",
        "header-link-color",
        "breadcrumbs-bg",
        "link-fg",
        "link-hover-color",
        "button-hover-bg",
        "default-button-bg",
    }
)
# The ones Django's admin/css/dark_mode.css gives a dark value of its own. A light value
# for them must not leak into dark mode, so COLORS sets them for the light theme only and
# dark keeps Django's value unless DARK_COLORS says otherwise. The rest look the same in
# both themes in the stock admin, and so they do here.
DARK_SENSITIVE = frozenset({"primary", "breadcrumbs-bg", "link-fg", "link-hover-color"})

KEYS = frozenset({"LOGO", "LOGO_ALT", "COLORS", "DARK_COLORS"})
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z")
# A static path, never a URL: no remote assets, no inline data.
REMOTE = re.compile(r"(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|/)")


def _config() -> Any:
    from .conf import get_setting

    return get_setting("BRANDING")


def _colors(value: Any) -> dict[str, str]:
    """The valid entries of one colour map, in a stable order. Invalid ones are dropped."""
    if not isinstance(value, dict):
        return {}
    return {
        name: color
        for name, color in sorted(value.items())
        if name in PALETTE and isinstance(color, str) and HEX_COLOR.match(color)
    }


def _logo_path(config: dict) -> str | None:
    logo = config.get("LOGO")
    if not logo or not isinstance(logo, str) or REMOTE.match(logo):
        return None
    return logo


def resolve() -> dict[str, Any]:
    """What the branding template renders, from validated settings only.

    Anything invalid is left out rather than rendered; the system check reports it. A
    logo the static storage cannot resolve (a manifest miss) means no logo, not an error
    page: the header text is still there.
    """
    config = _config()
    if not isinstance(config, dict):
        config = {}

    logo_url = None
    path = _logo_path(config)
    if path:
        from django.templatetags.static import static

        try:
            logo_url = static(path)
        except ValueError:
            logo_url = None

    # Decorative by default: the stock site name, the header's accessible name and its
    # link home, sits right beside the logo. LOGO_ALT is for a logo that says more.
    alt = config.get("LOGO_ALT")
    if not isinstance(alt, str):
        alt = ""

    colors = _colors(config.get("COLORS"))
    return {
        "logo_url": logo_url,
        "logo_alt": alt,
        "every_theme": {k: v for k, v in colors.items() if k not in DARK_SENSITIVE},
        "light": {k: v for k, v in colors.items() if k in DARK_SENSITIVE},
        "dark": _colors(config.get("DARK_COLORS")),
    }


def check_branding(app_configs=None, **kwargs):
    """Report every BRANDING value the template would silently leave out."""
    config = _config()
    if config is None:
        return []
    obj = "ADMIN_EXTENSIONS['BRANDING']"
    if not isinstance(config, dict):
        return [checks.Error(f"{obj} must be a dict.", obj=obj, id="django_extensions_admin.E201")]

    errors = []
    for key in sorted(set(config) - KEYS):
        errors.append(
            checks.Error(
                f"{obj} has an unknown key {key!r}.",
                hint=f"The keys are {', '.join(sorted(KEYS))}.",
                obj=obj,
                id="django_extensions_admin.E202",
            )
        )

    for key in ("COLORS", "DARK_COLORS"):
        value = config.get(key)
        if value is None:
            continue
        if not isinstance(value, dict):
            errors.append(
                checks.Error(
                    f"{obj}[{key!r}] must be a dict of colour variable names to hex colours.",
                    obj=obj,
                    id="django_extensions_admin.E203",
                )
            )
            continue
        for name, color in sorted(value.items(), key=lambda item: str(item[0])):
            if name not in PALETTE:
                errors.append(
                    checks.Error(
                        f"{obj}[{key!r}] names {name!r}, which is not a brand colour.",
                        hint=f"Use one of Django's own variables: {', '.join(sorted(PALETTE))}"
                        " (without the leading --).",
                        obj=obj,
                        id="django_extensions_admin.E204",
                    )
                )
            elif not (isinstance(color, str) and HEX_COLOR.match(color)):
                errors.append(
                    checks.Error(
                        f"{obj}[{key!r}][{name!r}] is {color!r}, not a hex colour.",
                        hint="Write it as #rgb or #rrggbb.",
                        obj=obj,
                        id="django_extensions_admin.E205",
                    )
                )

    logo = config.get("LOGO")
    alt = config.get("LOGO_ALT")
    if alt is not None and not isinstance(alt, str):
        errors.append(
            checks.Error(
                f"{obj}['LOGO_ALT'] must be a string.",
                obj=obj,
                id="django_extensions_admin.E207",
            )
        )
    if logo is not None:
        if not isinstance(logo, str) or not logo or REMOTE.match(logo):
            errors.append(
                checks.Error(
                    f"{obj}['LOGO'] is {logo!r}; it must be a static file path.",
                    hint="A path relative to your static files, like 'acme/admin-logo.svg'."
                    " Remote URLs and data: URIs are not used.",
                    obj=obj,
                    id="django_extensions_admin.E206",
                )
            )
        else:
            from django.apps import apps

            if apps.is_installed("django.contrib.staticfiles"):
                from django.contrib.staticfiles import finders

                if not finders.find(logo):
                    errors.append(
                        checks.Warning(
                            f"{obj}['LOGO'] {logo!r} is not found by the static files finders.",
                            hint="The header then shows its text without a logo.",
                            obj=obj,
                            id="django_extensions_admin.W201",
                        )
                    )
    return errors
