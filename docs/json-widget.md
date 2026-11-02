# JSON widget

Installed with the `jsonwidget` extra; see [installation](installation.md).

Drop-in replacement for the textarea on an existing `models.JSONField`. The form field
stays `forms.JSONField`; only the widget changes.

```python
from django.db import models
from django_extensions_admin import PrettyJSONWidget

class DeviceAdmin(admin.ModelAdmin):
    formfield_overrides = {models.JSONField: {"widget": PrettyJSONWidget}}
```

Project-wide instead, with no per-admin configuration:

```python
ADMIN_EXTENSIONS = {"JSON_WIDGET_DEFAULT": True}
```

An admin that declares its own JSONField widget always wins over the project-wide default.

Read-only rendering, in the same restrained style:

```python
from django_extensions_admin import JSONReadonlyMixin, readonly_json

class DeviceAdmin(JSONReadonlyMixin, admin.ModelAdmin):
    readonly_fields = ("last_report_pretty",)
    exclude = ("last_report",)
    last_report_pretty = readonly_json("last_report", short_description="Last report")
```

Django collects widget assets from *editable* fields, so an admin that shows JSON only
read-only has to ask for the stylesheet itself. `JSONReadonlyMixin` is that request and
nothing else. The plain-Django equivalent, if you prefer no import, is:

```python
class Media:
    css = {"all": ("django_extensions_admin/json-widget.css",)}
```

An admin that also has an editable JSON field already has the stylesheet. Without it the
output is still a readable `<pre>` with no colours. Read-only
JSON needs neither `PrettyJSONWidget` nor the buttons mixin.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `JSON_WIDGET_DEFAULT` | `False` | Install the widget as the admin-wide default for `models.JSONField`. |
| `JSON_MAX_PRETTY_CHARS` | `200000` | Above this, the value is shown exactly as stored and highlighting is off. |
| `JSON_INDENT` | `2` | Indentation used when re-indenting. |
| `JSON_REFORMAT_ON_BLUR` | `False` | Re-indent the field when it loses focus. Off, because it moves the caret. |

Per widget: `PrettyJSONWidget(indent=4, max_pretty_chars=50_000, reformat_on_blur=True)`.

## What the editor does

Indents the stored value on render, highlights keys/strings/numbers/literals, grows to fit
its content, validates as you type and marks the character the parser choked on. A
**Format** button re-indents on demand; there is no automatic rewrite unless you opt in.
Its corner handle resizes the field in both directions, and the colours, the Format button
and the fields below move with it. On a change form it widens up to the width of its row. The
next edit fits the height to the content again.

## Fidelity: what is preserved, and where

Three different things happen to your JSON, and only one of them is ours:

- **Rendering (server).** The widget re-indents with `json.loads`/`json.dumps` from the
  standard library. That is not where fidelity is lost: Django's own `forms.JSONField` has
  already run exactly that round trip before the widget sees anything. `bound_data()`
  parses the submitted text and `prepare_value()` dumps it again. Large integers such as
  `9007199254740993` survive, because Python's integers are arbitrary precision. `1.0E2`
  arrives as `100.0` and duplicate keys have already collapsed; Django did that, not the
  widget.
- **The Format button (browser).** Whitespace-only. The script rewrites the indentation
  between tokens and copies every string and number literal through byte for byte, so
  `9007199254740993`, `1.0E2`, `-0.0`, duplicate keys and key order all survive it. This is
  the case that matters, because it acts on text you just typed and have not sent anywhere:
  `JSON.parse`/`JSON.stringify` would have produced `9007199254740992` and `100`. Validity is
  decided by the browser's own `JSON.parse`; the re-indenter carries no JSON grammar of its
  own and only runs on text the parser has accepted.
- **Saving.** Goes through `forms.JSONField` and your database, which parse and re-serialise
  the value with their own semantics: duplicate keys collapse to the last one, and numbers
  become whatever Python and your column do with them. The widget does not change that and
  does not claim to.

Invalid input is never rewritten or discarded: text that does not parse is redisplayed
exactly as typed, so a failed save hands your own JSON back to you.

## When parts of it fail

- **No JavaScript**: a plain, readable, editable textarea with a sensible minimum height.
- **Stylesheet missing**: the script checks for a CSS custom property before it hides the
  textarea's own text. Without the stylesheet it builds no overlay at all, and the field
  stays readable.
- **Oversized value or a highlighting error**: the field drops to plain mode, and the
  textarea's own colours come back. The worst case is losing the colours, never the text.
- **Read-only fields**: plain `<pre>` markup rendered on the server, with no JavaScript
  involved at all; without the stylesheet it loses the colours, not the text.

Each of these is asserted in the browser tests, not assumed.

## Limitations

- It is a text editor, not a tree view, schema editor or diff tool.
- Marking the offset of a syntax error depends on the browser's parser message, which differs between
  engines and is absent in some.
- The colours follow typing, pasting and the Format button. A script of your own that sets
  the textarea's `value` directly should then dispatch an `input` event, or the colours and
  the height keep showing the old text until the next edit, blur or Format.
- Accessibility has not been audited. The field is a real `<textarea>` and the highlight layer is
  `aria-hidden`, but no assistive-technology testing has been done.

## Removing it

Delete the `formfield_overrides` entry or `JSON_WIDGET_DEFAULT`, and the read-only mixin and
`readonly_json(...)` fields, then `pip uninstall django-extensions-admin-jsonwidget`. Your JSONField
data stays exactly as stored: the widget never had its own format.
