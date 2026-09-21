"""Readonly rendering of JSON values, in the same restrained style as the editor."""

from __future__ import annotations

import json

from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from ..conf import get_setting
from .formatter import PUNCT, STRING, JSONFormatError, pretty_json_text, tokenize

__all__ = ["readonly_json", "render_json"]

CLASS_FOR_KIND = {
    "string": "admin-ext-json-string",
    "number": "admin-ext-json-number",
    "literal": "admin-ext-json-literal",
    "punct": "admin-ext-json-punct",
}


def highlight(text: str) -> str:
    """Wrap JSON tokens in spans. Returns escaped HTML; raises JSONFormatError."""
    pieces: list[str] = []
    cursor = 0
    tokens = tokenize(text)
    for index, token in enumerate(tokens):
        pieces.append(conditional_escape(text[cursor : token.start]))
        following = tokens[index + 1] if index + 1 < len(tokens) else None
        is_key = (
            token.kind == STRING
            and following is not None
            and following.kind == PUNCT
            and following.text == ":"
        )
        css_class = "admin-ext-json-key" if is_key else CLASS_FOR_KIND[token.kind]
        pieces.append(f'<span class="{css_class}">{conditional_escape(token.text)}</span>')
        cursor = token.end
    pieces.append(conditional_escape(text[cursor:]))
    return "".join(pieces)


def render_json(value, *, indent=None, max_pretty_chars=None) -> str:
    """Render *value* (a Python object or a JSON string) as readonly HTML.

    Everything is escaped: a stored ``"<script>"`` string is shown as text, never run.
    """
    if value is None:
        return mark_safe('<pre class="admin-ext-json-readonly admin-ext-json-empty">-</pre>')
    if indent is None:
        indent = get_setting("JSON_INDENT")
    if max_pretty_chars is None:
        max_pretty_chars = get_setting("JSON_MAX_PRETTY_CHARS")

    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    oversized = len(text) > max_pretty_chars
    if not oversized:
        try:
            text = pretty_json_text(text, indent=indent)
            body = highlight(text)
        except JSONFormatError:
            body = conditional_escape(text)
    else:
        body = conditional_escape(text)

    css = "admin-ext-json-readonly"
    if oversized:
        css += " admin-ext-json-readonly--plain"
    return mark_safe(f'<pre class="{css}"><code>{body}</code></pre>')  # noqa: S308


def readonly_json(field_name: str, *, short_description=None, indent=None):
    """Build a display callable for ``readonly_fields`` / ``list_display``.

    class ThingAdmin(admin.ModelAdmin):
        readonly_fields = ("payload_pretty",)
        payload_pretty = readonly_json("payload", short_description="Payload")
    """

    def display(self, obj=None):
        if obj is None:
            return ""
        return render_json(getattr(obj, field_name, None), indent=indent)

    display.short_description = short_description or field_name.replace("_", " ")
    display.admin_ext_json_readonly = field_name
    return display
