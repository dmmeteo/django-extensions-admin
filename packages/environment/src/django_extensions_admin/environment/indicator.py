"""Settings for the indicator, validated at the boundary.

``ADMIN_EXTENSIONS["ENVIRONMENT"]`` is a name, or a dict with NAME and optional COLOR,
POSITION and HEIGHT. Only a validated hex colour, one of two positions and a small integer
reach the page; the name is template text and is escaped like any other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.core import checks

__all__ = ["Indicator", "check_environment", "resolve"]

DEFAULT_COLOR = "#ba2121"  # the admin's own error red
DEFAULT_POSITION = "top"
DEFAULT_HEIGHT = 5
POSITIONS = ("top", "bottom")
MIN_HEIGHT, MAX_HEIGHT = 2, 12
MAX_NAME = 40
KEYS = frozenset({"NAME", "COLOR", "POSITION", "HEIGHT"})
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z")
OBJ = "ADMIN_EXTENSIONS['ENVIRONMENT']"


@dataclass(frozen=True)
class Indicator:
    name: str
    color: str
    text_color: str
    position: str
    height: int


def _raw() -> dict[str, Any]:
    from ..conf import get_setting

    value = get_setting("ENVIRONMENT")
    if isinstance(value, str):
        return {"NAME": value}
    return value if isinstance(value, dict) else {}


def _name(value: Any) -> str:
    return value.strip()[:MAX_NAME] if isinstance(value, str) else ""


def _valid_height(value: Any) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool) and MIN_HEIGHT <= value <= MAX_HEIGHT
    )


def _text_color(hex_color: str) -> str:
    """Black or white, whichever reads better on the accent (WCAG relative luminance)."""
    digits = hex_color[1:]
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    channels = []
    for i in (0, 2, 4):
        c = int(digits[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return "#000000" if luminance > 0.179 else "#ffffff"


def resolve() -> Indicator | None:
    """What the templates render, or None when no environment is named.

    An invalid colour, position or height falls back to its default and is reported by
    the system check; the name still shows, because hiding it would hide the warning.
    """
    raw = _raw()
    name = _name(raw.get("NAME"))
    if not name:
        return None
    color = raw.get("COLOR")
    color = color if isinstance(color, str) and HEX_COLOR.match(color) else DEFAULT_COLOR
    position = raw.get("POSITION")
    height = raw.get("HEIGHT")
    return Indicator(
        name=name,
        color=color.lower(),
        text_color=_text_color(color),
        position=position if position in POSITIONS else DEFAULT_POSITION,
        height=height if _valid_height(height) else DEFAULT_HEIGHT,
    )


def check_environment(app_configs=None, **kwargs):
    from ..conf import get_setting

    value = get_setting("ENVIRONMENT")
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [] if _name(value) else [_error("must name the environment.", "E302")]
    if not isinstance(value, dict):
        return [_error("must be a name or a dict.", "E301")]
    errors = [
        _error(
            f"has an unknown key {key!r}.", "E303", hint=f"The keys are {', '.join(sorted(KEYS))}."
        )
        for key in sorted(set(value) - KEYS, key=str)
    ]
    if "NAME" in value and not _name(value["NAME"]) and value["NAME"] != "":
        errors.append(_error("['NAME'] must be a non-empty string.", "E302"))
    if "COLOR" in value and not (
        isinstance(value["COLOR"], str) and HEX_COLOR.match(value["COLOR"])
    ):
        errors.append(
            _error(
                f"['COLOR'] is {value['COLOR']!r}, not a hex colour.",
                "E304",
                hint="Write it as #rgb or #rrggbb.",
            )
        )
    if "POSITION" in value and value["POSITION"] not in POSITIONS:
        errors.append(
            _error(f"['POSITION'] is {value['POSITION']!r}; use 'top' or 'bottom'.", "E305")
        )
    if "HEIGHT" in value and not _valid_height(value["HEIGHT"]):
        errors.append(
            _error(
                f"['HEIGHT'] is {value['HEIGHT']!r}; use an integer number of pixels from"
                f" {MIN_HEIGHT} to {MAX_HEIGHT}.",
                "E306",
            )
        )
    return errors


def _error(message: str, code: str, hint: str | None = None) -> checks.Error:
    return checks.Error(
        f"{OBJ} {message}", hint=hint, obj=OBJ, id=f"django_extensions_admin.{code}"
    )
