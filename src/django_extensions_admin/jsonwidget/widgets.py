"""A native-looking JSON editor for fields that already are ``models.JSONField``."""

from __future__ import annotations

import json
from typing import ClassVar

from django.contrib.admin.widgets import AdminTextareaWidget

from ..conf import get_setting
from .formatter import JSONFormatError, pretty_json_text

__all__ = ["PrettyJSONWidget"]


class PrettyJSONWidget(AdminTextareaWidget):
    """Textarea that shows JSON indented, highlighted and validated as you type.

    The form field stays ``forms.JSONField``; only the widget is swapped, so native
    validation, the model field and the stored value are untouched.
    """

    class Media:
        css: ClassVar[dict[str, tuple[str, ...]]] = {
            "all": ("django_extensions_admin/json-widget.css",)
        }
        js: ClassVar[tuple[str, ...]] = ("django_extensions_admin/json-widget.js",)

    def __init__(self, attrs=None, *, indent=None, max_pretty_chars=None, reformat_on_blur=None):
        self._indent = indent
        self._max_pretty_chars = max_pretty_chars
        self._reformat_on_blur = reformat_on_blur
        defaults = {
            "class": "vLargeTextField admin-ext-json",
            # A textarea never shrinks below `rows`, so keep it small and let the
            # script grow it; the stylesheet's min-height covers the no-JS case.
            "rows": 3,
            "spellcheck": "false",
            "autocomplete": "off",
            # Writing assistants inject their own overlay into the field, which lands
            # on top of the highlight layer and treats JSON as prose.
            "data-gramm": "false",
            "data-enable-grammarly": "false",
        }
        super().__init__({**defaults, **(attrs or {})})

    @property
    def indent(self) -> int:
        return get_setting("JSON_INDENT") if self._indent is None else self._indent

    @property
    def max_pretty_chars(self) -> int:
        if self._max_pretty_chars is None:
            return get_setting("JSON_MAX_PRETTY_CHARS")
        return self._max_pretty_chars

    @property
    def reformat_on_blur(self) -> bool:
        if self._reformat_on_blur is None:
            return bool(get_setting("JSON_REFORMAT_ON_BLUR"))
        return self._reformat_on_blur

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs["data-admin-ext-json"] = "1"
        attrs["data-admin-ext-max-chars"] = str(self.max_pretty_chars)
        attrs["data-admin-ext-indent"] = str(self.indent)
        if self.reformat_on_blur:
            attrs["data-admin-ext-blur-format"] = "1"
        return attrs

    def format_value(self, value):
        """Re-indent the compact string ``forms.JSONField.prepare_value`` produced.

        Text that does not parse is returned untouched - most importantly
        ``InvalidJSONInput``, the raw text kept after failed validation, so someone who
        submitted broken JSON gets their own input back instead of an empty box.
        """
        if not value or not isinstance(value, str):
            return value
        if len(value) > self.max_pretty_chars:
            return value
        try:
            return pretty_json_text(value, indent=self.indent)
        except JSONFormatError:
            return value

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        # Guard against a stray BOM or NBSP pasted from a document; json.loads would
        # reject the whole payload over a character the user cannot see.
        if isinstance(value, str):
            return value.replace("﻿", "")
        return value


def compact_json(value) -> str:
    """Serialise *value* the way ``forms.JSONField.prepare_value`` does."""
    return json.dumps(value, ensure_ascii=False)
