# django-extensions-admin

Small, additive utilities for the Django admin you already have: **buttons** and a
**JSON field editor**. No redesign, no base class you must inherit everywhere, no build
step, no runtime dependency beyond Django.

> **Independent project.** Inspired by the spirit of `django-extensions`, but not
> official, not affiliated with it, and it does not depend on it. The name is
> provisional and the package is not published on any package index.

## Philosophy

**Ordinary Django, with repetitive work removed.**

[PHILOSOPHY.md](PHILOSOPHY.md) is the accepted direction for feature selection, planning,
API design and review. Read it before proposing changes; use its short **Philosophy fit**
check in plans. Independent utilities, native Django primitives and the stock admin
experience come before breadth of features.

## Install

Not on PyPI. Install from the repository:

```bash
uv pip install "git+https://github.com/dmmeteo/django-extensions-admin"
```

Or build the wheel from a checkout:

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
from django_extensions_admin import admin as extensions_admin

@admin.register(Device)
class DeviceAdmin(extensions_admin.ButtonsMixin, admin.ModelAdmin):
    list_display = ("name", "region", "status")

    changelist_buttons = ["ping_all", "count_by_region", "purge"]
    changeform_buttons = ["run_diagnostics", "archive"]
    row_buttons = ["archive"]

    @extensions_admin.button(description="Ping all devices")
    def ping_all(self, request):
        return f"Pinged {self.get_queryset(request).update(status='pinged')} devices."

    @extensions_admin.button(description="Count by region", permissions=["view"])
    def count_by_region(self, request):
        return f"{self.get_queryset(request).count()} devices."

    @extensions_admin.button(description="Purge", permissions=["purge"], danger=True)
    def purge(self, request):
        deleted, _ = self.get_queryset(request).filter(archived=True).delete()
        return (f"Purged {deleted} rows.", "warning")

    def has_purge_permission(self, request):
        return request.user.has_perm("app.purge_device")

    @extensions_admin.button(description="Run diagnostics")
    def run_diagnostics(self, request, obj):
        return f"Diagnostics finished for {obj}."

    @extensions_admin.button(description="Archive", confirm="Archive this device?", danger=True)
    def archive(self, request, obj):
        obj.archived = True
        obj.save(update_fields=["archived"])
        return f"Archived {obj}."
```

`ModelAdmin`, `register` and everything else still come from `django.contrib.admin`.
`django_extensions_admin.admin` is a two-name namespace for this package's own API, not a
proxy for Django's. `from django_extensions_admin import ButtonsMixin, button` works too.

### Placement

| Option | Where | Handler |
| --- | --- | --- |
| `changelist_buttons` | the list toolbar | `(self, request)` |
| `changeform_buttons` | an existing object's change form | `(self, request, obj)` |
| `row_buttons` | every row of the list | `(self, request, obj)` |

The lists own placement **and order** — the decorator has no position flag. One object
handler can appear in both `changeform_buttons` and `row_buttons`: it is a single endpoint,
and it returns you to whichever page you used it from. Object buttons never appear on the
add form.

A changelist handler gets no queryset and no selection. Build what you need from
`self.get_queryset(request)`. For operations on *selected* rows, use an ordinary Django
action — buttons are not a second bulk-action system and **never** appear in the action
dropdown.

Declaring a name that does not exist, is not decorated with `@button`, or has the wrong
handler shape for its list raises `ImproperlyConfigured` with the class, the list and the
reason. It never silently does the wrong thing.

### `button(...)`

| Argument | Default | Meaning |
| --- | --- | --- |
| `description` | the method name | The label, like `@admin.action(description=...)`. |
| `permissions` | `None` | Names checked as `ModelAdmin.has_<name>_permission`, exactly as `@admin.action(permissions=...)`: **any** one of them is enough. |
| `confirm` | `None` | `True` or a question. The handler only runs from a server-rendered confirmation page (works without JavaScript). |
| `danger` | `False` | Destructive styling only. It is not a permission. |

Return `None` (default message), a string, a `(message, "success"/"warning"/"error"/...)`
pair, or an `HttpResponse` to take over the response entirely.

### What is enforced

- **Permissions are Django's.** `has_module_permission` is always required. With no
  `permissions` a button is a change operation: `has_change_permission(request, obj)` for the
  object in question. Declaring `permissions` **replaces** that default with `any()` over
  `has_<name>_permission`, the same rule Django applies to actions — so
  `permissions=["purge"]` means "whatever `has_purge_permission` says", not "change *and*
  purge". Custom policy goes in a `has_<name>_permission` method on your ModelAdmin.
- **Checked at the endpoint, not just at render time.** Hiding a button is cosmetic;
  guessing its URL gets a 403.
- **Method safety.** Every button is POST-only: `405` on GET, covered by Django's CSRF
  middleware. A handler that only reads still POSTs, and may return an `HttpResponse`.
- **Object lookup** goes through `ModelAdmin.get_object()`, so a row outside
  `get_queryset(request)` is a 404, not a leak.
- **List state** survives: buttons carry `_changelist_filters`, and the redirect afterwards
  puts you back on the same filtered, sorted, paginated page.
- **Descriptions are escaped.** HTML in a description is shown, never run.

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

Row buttons get their own column, appended automatically. Put `"row_buttons_column"`
anywhere in `list_display` to place it yourself, set `row_buttons_column_label` to rename
it, or set `auto_row_buttons_column = False` to leave it out.

### Removing buttons

Delete the three lists and the mixin. The decorated methods become ordinary methods; the
`@button` lines can go with them. No models, no migrations, no stored data.

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
button placement (changelist, change form, row, one handler in two places, and one denied
by permission) and
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

GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the part of
that gate which is reliable on a hosted Linux runner: lint and the test suite on Django 5.2
and 6.0. The wheel/install smoke and the browser smoke stay local.

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
