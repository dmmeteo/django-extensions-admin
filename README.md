# django-extensions-admin

Small, additive utilities for the Django admin you already have: **buttons** and a
**JSON field editor**. No redesign, no base class you must inherit everywhere, no build
step, no runtime dependency beyond Django.

> **Independent project.** Inspired by the spirit of `django-extensions`, but not
> official, not affiliated with it, and it does not depend on it. The name is
> provisional and nothing has been published anywhere.

## Philosophy

**Ordinary Django, with repetitive work removed.**

[PHILOSOPHY.md](PHILOSOPHY.md) is the accepted direction for feature selection, planning,
API design and review. Read it before proposing changes; use its short **Philosophy fit**
check in plans. Independent utilities, native Django primitives and the stock admin
experience come before breadth of features.

## Install

Local, unpublished. Build the wheel and install it:

```bash
uv build --wheel                      # -> dist/django_extensions_admin-0.1.0-py3-none-any.whl
uv pip install dist/*.whl
```

Add the app **before** `django.contrib.admin` so its optional project-wide default is in
place before admin autodiscovery runs:

```python
INSTALLED_APPS = [
    "django_extensions_admin",
    "django.contrib.admin",
    ...
]
```

(If it ends up after `django.contrib.admin`, the project-wide JSON default still applies -
it back-fills the admins that were already registered.)

## Buttons

```python
from django.contrib import admin
from django_extensions_admin import AdminExtensionsMixin, admin_button

@admin.register(Device)
class DeviceAdmin(AdminExtensionsMixin, admin.ModelAdmin):
    list_display = ("name", "region", "status")

    @admin_button("Ping all devices", scope="changelist")
    def ping_all(self, request, queryset):
        return f"Pinged {queryset.update(status='pinged')} devices."

    @admin_button("Ping shown devices", scope="changelist", filtered=True)
    def ping_shown(self, request, queryset):
        # queryset is what the current filters, search and ordering select
        return f"Pinged {queryset.update(status='pinged')} devices."

    @admin_button("Count by region", scope="changelist", read_only=True)
    def count_by_region(self, request, queryset):
        return f"{queryset.count()} devices."

    @admin_button("Run diagnostics", scope="object")
    def run_diagnostics(self, request, obj):
        return f"Diagnostics finished for {obj}."

    @admin_button("Archive", scope="row", confirm="Archive this device?", danger=True)
    def archive(self, request, obj):
        obj.archived = True
        obj.save(update_fields=["archived"])
        return f"Archived {obj}."

    @admin_button("Purge", scope="changelist", permission="app.purge_device", danger=True)
    def purge(self, request, queryset):
        return (f"Purged {queryset.filter(archived=True).delete()[0]} rows.", "warning")
```

### `admin_button(label, ...)`

| Argument | Default | Meaning |
| --- | --- | --- |
| `scope` | `"object"` | `"changelist"` (handler gets a queryset), `"object"` (change form, gets the instance), `"row"` (one per list row, gets the instance). |
| `read_only` | `False` | The handler does not change data: renders a link, GET is accepted, **view** permission is enough. Everything else is POST-only, CSRF-protected and needs **change** permission. |
| `filtered` | `False` | Changelist scope only: hand the handler the rows currently on screen instead of all of them. |
| `permission` | `None` | Extra requirement: a permission string, an iterable of them, or a callable `(request, obj)`. |
| `confirm` | `None` | `True` or a question. The action only runs from a server-rendered confirmation page (works without JavaScript). |
| `danger` | `False` | Destructive styling only. |
| `name` | method name | URL/segment name. |
| `success_message` | `None` | Message when the handler returns `None`. |

Return `None` (default message), a string, a `(message, "success"/"warning"/"error"/...)`
pair, or an `HttpResponse` to take over the response entirely.

### What is enforced

- **Permissions are additive.** `permission=` can only *narrow* access. The ModelAdmin's own
  `has_module_permission` plus `has_view_permission` (read-only buttons) or
  `has_change_permission` (everything else) is checked first, for the object in question.
  A custom callable returning `True` cannot hand out an action the ModelAdmin would refuse.
- **Checked at the endpoint, not just at render time.** Hiding a button is cosmetic;
  guessing its URL gets a 403.
- **Method safety.** Mutating buttons answer `405` to GET and are covered by Django's CSRF
  middleware.
- **Object lookup** goes through `ModelAdmin.get_object()`, so a row outside
  `get_queryset(request)` is a 404, not a leak.
- **List state** survives: buttons carry `_changelist_filters`, and the redirect afterwards
  puts you back on the same filtered, sorted, paginated page.
- **Labels are escaped.** HTML in a label is shown, never run.

### Markup: why buttons are not wrapped in `<form>`

The changelist rows are rendered *inside* Django's own `#changelist-form`. A nested
`<form>` is invalid HTML and browsers drop it, so the buttons would quietly stop working.
Instead the mixin renders one empty `<form id="admin-ext-action-form">` outside that form,
and every button points at it with `form="admin-ext-action-form"` and `formaction="…"`.
This is valid HTML5, it is verified in a real browser, and it means a button submits
*only itself*: bulk actions and pending `list_editable` edits are left alone.

The mixin sets `change_list_template` / `change_form_template` to thin templates that
extend the stock admin ones. If your project already overrides those, make your own
template extend `django_extensions_admin/change_list.html` instead.

Row buttons get their own column, appended automatically. Put `"admin_ext_row_buttons"`
anywhere in `list_display` to place it yourself, or set
`admin_ext_auto_row_column = False` to leave it out.

## JSON widget

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
from django_extensions_admin import readonly_json

class DeviceAdmin(admin.ModelAdmin):
    readonly_fields = ("last_report_pretty",)
    exclude = ("last_report",)
    last_report_pretty = readonly_json("last_report", short_description="Last report")
```

### Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `JSON_WIDGET_DEFAULT` | `False` | Install the widget as the admin-wide default for `models.JSONField`. |
| `JSON_MAX_PRETTY_CHARS` | `100000` | Above this, the value is shown exactly as stored and highlighting is off. |
| `JSON_INDENT` | `2` | Indentation used when re-indenting. |
| `JSON_REFORMAT_ON_BLUR` | `False` | Re-indent the field when it loses focus. Off, because it moves the caret. |

Per widget: `PrettyJSONWidget(indent=4, max_pretty_chars=50_000, reformat_on_blur=True)`.

### What the editor does

Indents the stored value on render, highlights keys/strings/numbers/literals, grows to fit
its content, validates as you type and marks the character the parser choked on. A
**Format** button re-indents on demand; there is no automatic rewrite unless you opt in.

### Fidelity: text vs. saving — read this

Re-indenting is **whitespace-only**. The formatter (in Python and in JavaScript) never
parses JSON into objects and back: every string and number literal is copied byte for byte.
So `9007199254740993`, `1.0E2`, `-0.0`, duplicate keys and key order all survive
re-indentation and the Format button unchanged. `JSON.parse`/`JSON.stringify` would not.

**This guarantee covers the text in the editor, not a save.** Saving goes through
`forms.JSONField` and your database, which parse and re-serialise the value with their own
semantics: duplicate keys collapse to the last one, and numbers become whatever Python and
your database column do with them. The widget does not change that and does not claim to.

Invalid input is never rewritten or discarded: text that does not parse is redisplayed
exactly as typed, so a failed save hands your own JSON back to you.

### When parts of it fail

- **No JavaScript**: a plain, readable, editable textarea with a sensible minimum height.
- **Stylesheet missing**: the script checks for a CSS custom property before it hides the
  textarea's own text. Without the stylesheet it builds no overlay at all, and the field
  stays readable.
- **Oversized value or a highlighting error**: the field drops to plain mode - the
  textarea's own colours come back. The worst case is losing the colours, never the text.

Each of these is asserted in the browser tests, not assumed.

## Demo

```bash
bash scripts/demo.sh
# http://127.0.0.1:8765/admin/
# demo/demo (superuser)   operator/operator (staff, cannot purge)
```

Loopback only, a disposable SQLite file, and entirely generated data. The demo shows every
button scope (global, filtered, read-only, object, row, and one denied by permission) and
the JSON cases worth seeing: nested values, Unicode, numbers JavaScript cannot represent,
HTML-looking strings, a >100 KB payload in plain mode, and a read-only rendering.

`DEMO_PORT=9000 bash scripts/demo.sh` changes the port.

## Verify

```bash
bash scripts/verify.sh
```

Lint (Ruff + `node --check`), naming check, wheel build with an asset manifest check, a
clean-install import smoke from the wheel, the test suite on both supported Django
versions, and the headless-browser smoke with screenshots into `artifacts/`.

## Tested versions

Exactly what the gate runs, and nothing is claimed beyond it:

| | Version |
| --- | --- |
| Python | CPython 3.13 |
| Django | 5.2 LTS and 6.0 |
| Browser | Chromium via Playwright 1.63 (headless) |
| OS | Linux x86-64 |

`requires-python = ">=3.12"` and `Django>=5.2,<7` are the declared bounds. Other
combinations inside those bounds are plausible but **untested**; Windows, macOS, Firefox
and Safari are untested.

## Limitations

- Buttons are buttons. There is no workflow engine, no action-form builder, no chaining and
  no persisted run history.
- Long-running handlers block the request; hand work to your own task runner.
- The JSON editor is a text editor, not a tree view, schema editor or diff tool.
- Error-offset marking depends on the browser's parser message, which differs between
  engines and is absent in some.
- Accessibility has not been audited. The field is a real `<textarea>` and the highlight
  layer is `aria-hidden`, but no assistive-technology testing has been done.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for feature candidates and
[ARCHITECTURE.md](ARCHITECTURE.md) for the proposed structure and incremental implementation slices.

## License

MIT, see [LICENSE](LICENSE).
