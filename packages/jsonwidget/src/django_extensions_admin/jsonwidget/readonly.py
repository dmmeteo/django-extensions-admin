"""Readonly rendering of JSON values, in the same restrained style as the editor."""

from __future__ import annotations

import json
import re
from typing import ClassVar

from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from ..conf import get_setting

__all__ = ["JSONReadonlyMixin", "readonly_json", "render_json"]

# One pass over text ``json.dumps`` produced: a string followed by a colon is a key, then
# plain strings, numbers, literals and punctuation. Anything unmatched - whitespace, or the
# text of a value that did not parse - stays plain. Colouring is presentation, so it never
# needs a grammar; the browser mirrors this regex in json-widget.js.
TOKEN_RE = re.compile(
    r'("(?:\\.|[^"\\])*")(\s*:)'
    r'|("(?:\\.|[^"\\])*")'
    r"|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    r"|\b(true|false|null)\b"
    r"|([{}\[\],:])"
)

CLASS_FOR_GROUP = {
    1: "admin-ext-json-key",
    2: "admin-ext-json-punct",
    3: "admin-ext-json-string",
    4: "admin-ext-json-number",
    5: "admin-ext-json-literal",
    6: "admin-ext-json-punct",
}


class JSONReadonlyMixin:
    """Adds the JSON stylesheet to an admin that only *renders* JSON.

    ``readonly_json`` output is styled by the same stylesheet as the editor, and Django
    collects widget media only for editable fields. An admin whose JSON fields are all
    read-only therefore has to ask for the asset itself - this is that request, and it is
    nothing but a plain Django ``class Media``::

        class ThingAdmin(JSONReadonlyMixin, admin.ModelAdmin):
            readonly_fields = ("payload_pretty",)

    Without it the output is still perfectly readable, just unstyled.
    """

    class Media:
        css: ClassVar[dict[str, tuple[str, ...]]] = {
            "all": ("django_extensions_admin/json-widget.css",)
        }


def highlight(text: str) -> str:
    """Wrap JSON tokens in spans. Returns escaped HTML."""
    pieces: list[str] = []
    cursor = 0
    for match in TOKEN_RE.finditer(text):
        pieces.append(conditional_escape(text[cursor : match.start()]))
        for group, css_class in CLASS_FOR_GROUP.items():
            captured = match.group(group)
            if captured is not None:
                pieces.append(f'<span class="{css_class}">{conditional_escape(captured)}</span>')
        cursor = match.end()
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
            text = json.dumps(json.loads(text), indent=indent, ensure_ascii=False)
        except ValueError:
            # Not JSON - a plain CharField, or a value stored before the field was one.
            body = conditional_escape(text)
        else:
            body = highlight(text)
    else:
        body = conditional_escape(text)

    css = "admin-ext-json-readonly"
    if oversized:
        css += " admin-ext-json-readonly--plain"
    return mark_safe(f'<pre class="{css}"><code>{body}</code></pre>')  # noqa: S308


def readonly_json(field_name: str, *, short_description=None, indent=None):
    """Build a display callable for ``readonly_fields`` / ``list_display``.

    class ThingAdmin(JSONReadonlyMixin, admin.ModelAdmin):
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
