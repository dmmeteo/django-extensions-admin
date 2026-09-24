# django-extensions-admin

Small, additive utilities for the Django admin you already have: **buttons**, a
**JSON field editor**, **range filters**, **choice filters** and an opt-in
**management-command runner**. No redesign, no base class you must inherit everywhere, no
build step, no runtime dependency beyond Django. The command runner alone needs a Django
Tasks backend, which you install only if you use it.

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
from django_extensions_admin import JSONReadonlyMixin, readonly_json

class DeviceAdmin(JSONReadonlyMixin, admin.ModelAdmin):
    readonly_fields = ("last_report_pretty",)
    exclude = ("last_report",)
    last_report_pretty = readonly_json("last_report", short_description="Last report")
```

Django collects widget assets from *editable* fields, so an admin that shows JSON only
read-only has to ask for the stylesheet itself. `JSONReadonlyMixin` is that request and
nothing else - the plain-Django equivalent, if you prefer no import, is:

```python
class Media:
    css = {"all": ("django_extensions_admin/json-widget.css",)}
```

An admin that also has an editable JSON field already has the stylesheet, and without it
the output is still a perfectly readable `<pre>` - only the colours are missing. Read-only
JSON needs neither `PrettyJSONWidget` nor the buttons mixin.

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

### Fidelity: what is preserved, and where

Three different things happen to your JSON, and only one of them is ours:

- **Rendering (server).** The widget re-indents with `json.loads`/`json.dumps` from the
  standard library. That is not where fidelity is lost: Django's own `forms.JSONField` has
  already run exactly that round trip - `bound_data()` parses the submitted text and
  `prepare_value()` dumps it again - before the widget sees anything. Large integers such as
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

### When parts of it fail

- **No JavaScript**: a plain, readable, editable textarea with a sensible minimum height.
- **Stylesheet missing**: the script checks for a CSS custom property before it hides the
  textarea's own text. Without the stylesheet it builds no overlay at all, and the field
  stays readable.
- **Oversized value or a highlighting error**: the field drops to plain mode - the
  textarea's own colours come back. The worst case is losing the colours, never the text.
- **Read-only fields**: plain `<pre>` markup rendered on the server, with no JavaScript
  involved at all; without the stylesheet it loses the colours, not the text.

Each of these is asserted in the browser tests, not assumed.

## Range filters

Inclusive from/to bounds for a date, datetime or numeric column, as an ordinary
`list_filter` entry. Nothing is registered globally, so a field only gets a range filter
where you ask for one.

```python
from django.contrib import admin
from django_extensions_admin import DateRangeFilter, DateTimeRangeFilter, NumericRangeFilter

@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_filter = [
        ("recorded_on", DateRangeFilter),
        ("recorded_at", DateTimeRangeFilter),
        ("value", NumericRangeFilter),
        "device",
    ]
```

That is the whole adoption: no mixin, no setting, no custom `AdminSite`, no template of
your own. The sidebar gets two native inputs and an **Apply** button - no JavaScript at all.

| Filter | Field types | Input | Query parameters |
| --- | --- | --- | --- |
| `DateRangeFilter` | `DateField`, `DateTimeField` | `<input type="date">` | `<field>__range__gte`, `<field>__range__lte` |
| `DateTimeRangeFilter` | `DateTimeField` | `<input type="datetime-local">` | the same two |
| `NumericRangeFilter` | `IntegerField`, `FloatField`, `DecimalField` | `<input type="number">` | the same two |

Both parameters are optional: one bound alone is a one-sided range, not an error. They are
declared as the filter's expected parameters, so the changelist hands them to the filter
instead of treating them as raw ORM lookups. Attaching a filter to a field type it cannot
read raises `ImproperlyConfigured` at the point the changelist builds its filters, naming
the class and the field.

### What the bounds mean

- **A `DateField`** is filtered with `__gte` and `__lte` on the dates themselves. Both ends
  are included.
- **A `DateTimeField` under `DateRangeFilter`** means whole days: `__gte` at midnight
  starting the first day and `__lt` at midnight after the last. Half-open at the top on
  purpose - an inclusive `__lte` would have to name a last instant, and would then drop
  whatever a column with more precision than that instant still holds.
- **`DateTimeRangeFilter`** includes both instants, to the minute the browser offers.
- **`NumericRangeFilter`** includes both numbers, parsed by the model field's own form
  field. A `DecimalField` therefore brings its own precision and the matching input step,
  and an `IntegerField` its column's range.

**Timezone.** Every date-like bound is read in Django's *active* timezone, so "the 3rd"
means the reader's 3rd, not UTC's. Parsing is Django's own `forms.DateField` /
`forms.DateTimeField`, which already route through `from_current_timezone()`; the whole-day
boundaries use `timezone.make_aware()`. With `USE_TZ = False` the bounds stay naive, like
the column. A `datetime-local` input has no timezone picker, so the time you type is a
local wall-clock time, not an offset.

### When input is wrong

None of these raises, and none of them widens the result. The filter runs on the queryset
your `ModelAdmin` already authorized, so it can only take rows away from it.

| Input | What happens |
| --- | --- |
| Neither bound | No filtering. The form still renders. |
| One bound only | A one-sided range. Supported, not an error. |
| A bound the field cannot read | The error is shown under that input, and the list is empty. |
| Start after end | "The start of the range is after its end." under the form, and the list is empty. |

An empty list is the point: a bound nobody can read must not quietly behave like no filter
at all. The text you typed is handed straight back in the HTML, though a browser's
`<input type="number">` will decline to *display* something that is not a number.

Submitting the form is an ordinary GET. It carries the rest of the query string - the
search term, the ordering, the other filters - as hidden inputs, and drops the page number,
because a new range starts at page one. **Clear** removes that filter's own two parameters
and nothing else. Each range filter is its own form, so applying two of them is two
submits; the second carries the first.

### Removing range filters

Delete the `list_filter` entry and the import. There is no model field, no migration, no
stored state and no data format of ours anywhere - bookmarked URLs simply stop filtering.
Django's own `DateFieldListFilter` and `admin.EmptyFieldListFilter` are drop-in
replacements for part of it if you want to keep something.

## Choice filters

A compact dropdown for one value, or a checkbox list for several values of the same field,
ORed together. Both are ordinary `list_filter` entries. Nothing is registered globally.

```python
from django.contrib import admin
from django_extensions_admin import ChoiceFilter, MultipleChoiceFilter

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_filter = [
        ("region", ChoiceFilter),          # one value, from a <select>
        ("status", MultipleChoiceFilter),  # any of several values
        ("tags", MultipleChoiceFilter),    # works across many-to-many, one row per device
        "archived",
    ]
```

Selecting two tags lists the devices that carry either one. Values of *different* fields
still narrow each other, as every other filter does.

| Field | Options | Query parameter |
| --- | --- | --- |
| `ForeignKey`, `OneToOneField`, `ManyToManyField`, reverse relations | the related objects, in the related admin's ordering | `<field>__<pk>__exact`, plus `<field>__isnull` for the empty choice |
| Any field with `choices` | the field's choices | `<field>__exact`, plus `<field>__isnull` when `None` is a choice |
| `CharField`, `IntegerField`, `DecimalField`, `UUIDField` without choices | the distinct values in the admin's own queryset | `<field>`, plus `<field>__isnull` when a row is `NULL` |

These are Django's own parameter names, the ones its default filter for that field uses.
Several values arrive as a repeated key, `?status=idle&status=running`. Values are never
joined into one comma-separated string, so a value containing a comma, `&`, `%` or quotes
stays one value. A path through a relation (`"device__region"`) works the same way. Any
other field type (dates, booleans, JSON, text, floats) raises `ImproperlyConfigured` when
the changelist builds its filters, naming the class and the field. Dates have the range
filters, and booleans are already compact in Django's default filter.

Each filter is a GET form with an **Apply** button, in the stock sidebar markup. The
checkbox list is the stock `<ul>`, and a selected row gets the stock `selected` marker. The
form carries the rest of the query string (search, ordering, other filters) and drops the
page number. **Clear** removes exactly that filter's own parameters. It leaves alone a
range filter on the same column (`sequence` vs `sequence__range__gte`). With `show_facets`,
each option shows its count.

### Search over long lists

A filter with more than 10 options gets a search box above them. It hides the options that
don't match; the selection itself doesn't change, so a checked box you've searched out of
view is still submitted. It is a small vanilla script, `choice-filters.js`, and it only
searches options already on the page: no request, no autocomplete endpoint. Without
JavaScript there's no search box, and both filters work exactly the same. To change the
threshold, subclass:

```python
class TagFilter(MultipleChoiceFilter):
    search_threshold = 0  # always offer search
```

### What each filter reads

- **`MultipleChoiceFilter`** reads every value of its parameter and ORs them. It also
  offers the field's empty choice, shown with the admin's empty-value display (or the label
  of a `None` choice), as one more box.
- **`ChoiceFilter`** reads one value. When the URL repeats the key, it uses the last one,
  which is the one the dropdown can show. It has no empty choice: a `<select>` sends one
  parameter, and "empty" is a different parameter in Django. Use `MultipleChoiceFilter` or
  Django's `admin.EmptyFieldListFilter` for that.
- An empty value is the dropdown's own **All**, so blank strings are not offered as an
  option in either filter. `admin.EmptyFieldListFilter` covers them.

### Values it cannot offer

None of these raises or redirects, and none of them widens the result. The filter runs on
the queryset your `ModelAdmin` already authorized, so it can only take rows away.

| Input | What happens |
| --- | --- |
| A value the field cannot read (`?tags__id__exact=nope`) | Matches nothing. Alone, the list is empty. |
| An unreadable value next to readable ones | The readable ones still apply. The unreadable one adds no rows. |
| A readable value that is not an offered option | It is filtered exactly like any other value, which usually means no rows. |
| `<field>__isnull` with anything but `True`/`1` | Matches nothing. It doesn't mean "not empty", which ORed with the rest would mean nearly everything. |

In every one of these cases the sidebar says "A selected value is not one of the choices."
and shows **Clear**, so the widget never claims "All" while the list is filtered.

### Removing choice filters

Replace `("status", MultipleChoiceFilter)` with `"status"`. There is no model field, no
migration and no stored state. Bookmarked URLs keep working, because the parameter names are
Django's and Django also ORs a repeated key. The one exception is "empty" together with a
value, which Django's own filter reads as both at once and therefore matches nothing.

## Management commands

Launch an explicit allow-list of management commands from the admin. A Django Tasks worker
runs them, so the admin request never waits, and the user who launched a run sees its status
and output. Adoption is explicit: installing the app adds no route, and none of the other
features imports a Tasks package.

```python
# admin.py - admin modules are imported in every process, the worker included
from django import forms
from django_extensions_admin import commands

class RebuildIndexForm(forms.Form):
    batch_size = forms.IntegerField(min_value=1, initial=500)   # --batch-size
    dry_run = forms.BooleanField(required=False)                # --dry-run

commands.register("clearsessions", permission="sessions.delete_session")
commands.register(
    "rebuild_index",
    form=RebuildIndexForm,
    permission="search.rebuild_index",
    description="Rebuild the search index",
)
```

```python
# urls.py - before admin.site.urls, which ends with a catch-all
urlpatterns = [
    path("admin/commands/", commands.urls(admin.site)),
    path("admin/", admin.site.urls),
]
```

### Setup

Install the backend. Use the line for your Django version:

```bash
uv pip install django-tasks-db               # Django 6.0: django.tasks is built in
uv pip install "django-tasks-db[compat]"     # Django 5.2: adds the django-tasks backport
```

`[compat]` pins Django below 6.0, so do not use it on 6.0. django-extensions-admin has no
extra for this: a single extra cannot be right for both Django versions. Both packages are
BSD-3-Clause.

```python
INSTALLED_APPS += ["django_tasks_db"]          # plus "django_tasks" on Django 5.2
TASKS = {"commands": {"BACKEND": "django_tasks_db.DatabaseBackend"}}
ADMIN_EXTENSIONS = {"COMMANDS_TASK_BACKEND": "commands"}
```

Run `manage.py migrate` to create the queue table, which lives in your own database. Then run
a worker for that alias under your process supervisor:

```bash
python manage.py db_worker --backend commands --no-reload
python manage.py prune_db_task_results --backend commands --queue-name '*' --min-age-days 14
```

- **`--no-reload`:** reloading defaults to `DEBUG`.
- **Stop grace period:** give the worker one at least as long as your longest command. One
  SIGTERM lets the running command finish; a second one interrupts it.
- **Pruning:** schedule the second command. Results are kept until you prune them.
- **Lost runs:** nothing recovers a run whose worker was killed. The page then warns that the
  run may be stuck (below), and it is not retried.

The package adds no menu entry. Link to `/admin/commands/` from wherever suits your admin.

### Registering a command

`register(name, *, permission, form=None, description=None)`

- **`name`** is the management command. Nothing unregistered can be launched, whatever the
  browser sends.
- **`permission`** is required, as `"app_label.codename"` and checked with
  `user.has_perm`. Use an existing model permission or a custom `Meta.permissions` entry.
- **`form`** is an ordinary `forms.Form`. Its field names are the command's option names
  (`dest`), and its `cleaned_data` becomes the `call_command()` keyword arguments. Leave it
  out for a command without options; the page then asks for an explicit Run.
- **`description`** is the label. It defaults to the command name.

The system checks catch these mistakes:
- an unknown command;
- a field that is not one of the command's options;
- a missing, unknown or inline backend.

`register()` itself refuses these, as `ImproperlyConfigured`:
- a duplicate;
- a permission not written as `"app_label.codename"`;
- file fields;
- fields named `stdout`, `stderr` or `interactive`.

### Pages and statuses

`/admin/commands/` lists the registered commands the user may run. It is not a list of runs.
Each command has a stock admin form. **Run** posts it, queues the run and redirects to that
run's result page:

| Status | Shown when |
| --- | --- |
| Queued | Waiting for a worker. The page reloads itself every 3 s with a `<meta>` refresh; no JavaScript. |
| Running | A worker has claimed it. |
| Succeeded | Captured `stdout` and `stderr`, escaped. |
| Failed | The exception type and message, plus the output written before it. Never the traceback. |
| Unavailable | The result was pruned, is unknown, or belongs to a backend alias that is no longer configured. |

A run still queued or running after `COMMANDS_STALE_AFTER` stops reloading and shows a
warning. A running run's warning says the worker may have stopped. A queued run's warning asks
whether a worker is serving the alias. Runs are never retried automatically.

### What is enforced

- **Launch is POST-only and CSRF-protected.** A GET shows the form and queues nothing.
- **Every view runs through `admin_site.admin_view`.** An active staff login is required, and
  each view checks the command's permission itself. Hiding a link is not a security boundary.
- **The payload is the form's submitted values, as JSON, plus the command key and user id.**
  Before queueing, the values are validated a second time; any that would come back
  different are refused.
- **The worker trusts none of the payload.** It looks the key up in its own registry,
  requires the launching user to be active and still permitted, and validates the options
  against the registered form. Only then does it call `call_command()`. It passes
  `interactive=False` when the command has that option.
- **Result pages are for the initiator only.** A result is reached through a signed reference
  binding the result id, backend alias, command and initiating user. Anyone else gets a 404,
  superusers included. The permission is checked again on every view. A raw task id grants
  nothing.
- **django-tasks-db's own admin is separate.** It registers a "Task Results" admin for its
  model. Superusers, and staff holding its `django_tasks_db` view permission, see every task
  there, with its arguments and output. Grant that permission deliberately, or
  `admin.site.unregister(DBTaskResult)` if the initiator-only pages should be the only view.
- **Output is bounded and escaped.** `COMMANDS_OUTPUT_LIMIT` characters are kept per stream,
  cut in the worker and again on the page. HTML-looking output is shown as text.
- **Misconfiguration is refused, never worked around.** An unset or unknown alias, the
  `ImmediateBackend` or `DummyBackend`, or a backend that cannot read results back produces
  a system check error. The pages show the same error and offer no Run button. A POST
  returns 503. Nothing ever runs inline.
- **Queue failures are shown, not hidden.** If the backend refuses an enqueue, the page says
  so with a 503. It shows no "queued" message.

### Transactions and `ATOMIC_REQUESTS`

A run is queued with `transaction.on_commit`, so a rolled-back transaction never publishes
work. There is also no run-history model, so the launch view can only show a result once the
task exists. Two things follow:

- **The launch view opts out of `ATOMIC_REQUESTS`.** It uses
  `transaction.non_atomic_requests` for every **database** alias in `DATABASES`, which is a
  separate thing from the Tasks alias. It writes no application data of its own. With
  `ATOMIC_REQUESTS = True` launching therefore works as usual, and the task row is committed
  before the worker looks for it.
- **An open transaction makes the launch fail.** If a database connection is still inside
  `atomic()` when the view runs, for example because your middleware wraps requests in a
  transaction, the launch is refused with an error. It is not deferred, because a deferred
  run could not return a reference.

### Settings

All under `ADMIN_EXTENSIONS`:

| Key | Default | Meaning |
| --- | --- | --- |
| `COMMANDS_TASK_BACKEND` | `None` | The `settings.TASKS` alias that runs commands. Required; Django's `"default"` is never assumed. |
| `COMMANDS_OUTPUT_LIMIT` | `20000` | Characters kept from each of stdout and stderr. |
| `COMMANDS_STALE_AFTER` | `1800` | Seconds before a queued or running run is reported as possibly stuck. |

### Backends

**django-tasks-db** is the only tested backend:
- Django 6.0: `django.tasks`, native.
- Django 5.2: `django_tasks`, through `[compat]`.

Other backends that can read results back get a system check warning (`W101`), not a promise.
Celery (django-tasks-celery 0.1.1) is not supported: lost and unknown results look like
pending ones, and rolled-back transactions still dispatch. The evidence is in
[the decision note](docs/decisions/actions-and-task-execution.md).

### Removing the command runner

1. Remove the `commands.urls(...)` line, the `commands.register(...)` calls and
   `COMMANDS_TASK_BACKEND`. The commands remain ordinary management commands.
2. Let queued runs finish, then prune or drop the results. They live in django-tasks-db's
   table, not ours.
3. Remove `django_tasks_db`/`django_tasks` from `INSTALLED_APPS` and uninstall them if
   nothing else uses them.

The package itself has no model and no migration.

## Demo

```bash
bash scripts/demo.sh
# http://127.0.0.1:8765/admin/
# http://127.0.0.1:8765/admin/commands/   (a db_worker runs beside the server)
# demo/demo (superuser)   operator/operator (staff, cannot purge or run commands)
```

Loopback only, a disposable SQLite file, and entirely generated data. The demo shows every
button placement (changelist, change form, row, one handler in two places, and one denied
by permission) and
the JSON cases worth seeing: nested values, Unicode, numbers JavaScript cannot represent,
HTML-looking strings, a >100 KB payload in plain mode, and a read-only rendering. Readings
and devices carry dates, instants and numbers for the range filters, with sightings just
after and just before local midnight so the timezone boundary is visible. Devices also
have a region dropdown and status and tag checkbox lists. There are fifteen tags,
including `r&d` and `rack 4, bay 2`, enough to bring up the search box. On Readings you pick
the device from a searchable dropdown. The command runner offers one read-only
`demo_report` command with a region choice, a checkbox and a free-text note that is printed
verbatim. The note is where HTML-looking output shows up as plain text.

`DEMO_PORT=9000 bash scripts/demo.sh` changes the port.

## Verify

```bash
bash scripts/verify.sh
```

The gate runs, in order:
- lint (Ruff + `node --check`) and a naming check;
- a wheel build, checked against an asset manifest and for Django being its only dependency;
- a clean-install import smoke from the wheel, **with no Tasks package installed**;
- the test suite on both supported Django versions, each with its documented
  django-tasks-db install;
- the command runner end to end against a **separately started `db_worker` process** on both
  versions;
- the headless-browser smoke, with screenshots into `artifacts/`.

The worker journeys also run against PostgreSQL: set `WORKER_PG=host:port` (user, password
and database `deadmin`) and run
`DJANGO_SETTINGS_MODULE=worker_tests.settings python tests/runtests.py worker_tests`.

GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the part of
that gate which is reliable on a hosted Linux runner: lint, the test suite and the worker
journeys on Django 5.2 and 6.0. The wheel/install smoke and the browser smoke stay local.

## Tested versions

Exactly what the gate runs, and nothing is claimed beyond it:

| | Version |
| --- | --- |
| Python | CPython 3.13 |
| Django | 5.2 LTS and 6.0 |
| Command-runner backend | django-tasks-db 0.13.0 (with django-tasks 0.12 on 5.2), SQLite; PostgreSQL 16 checked separately |
| Browser | Chromium via Playwright 1.63 (headless) |
| OS | Linux x86-64 |

`requires-python = ">=3.12"` and `Django>=5.2,<7` are the declared bounds. Other
combinations inside those bounds are plausible but **untested**; Windows, macOS, Firefox
and Safari are untested.

## Limitations

- Buttons are buttons. There is no workflow engine, no action-form builder, no chaining and
  no persisted run history.
- Long-running button handlers block the request; hand the work to your own task runner, or
  register it as a command for the command runner.
- The command runner:
  - **Visibility.** It shows a run to its initiator only. There is no run list, history or
    dashboard, and no way to show a run to another admin.
  - **What it runs.** It passes options only: no positional arguments and no file uploads.
    The form is built with `data=` alone, without the request.
  - **What it captures.** Only `self.stdout` and `self.stderr` are captured, not `print()`
    or logging. Output arrives when the run finishes; nothing is streamed.
  - **What it does not do.** No cancellation, retries, scheduling or priorities. A run whose
    worker was killed stays "running" until it is pruned.
  - **Where it launches from.** Launching is refused from inside an open database
    transaction (see above).
- The JSON editor is a text editor, not a tree view, schema editor or diff tool.
- Range filters are two bounds on one field. No saved presets, no relative shortcuts
  ("last 7 days" is Django's own `DateFieldListFilter`), no `__in` lists, no query builder.
- Range filters show no facet counts. Django's counts are per choice, and a range is not a
  list of choices; `show_facets` still works for every other filter on the page.
- Choice filters pick values; they do not build queries. No AND mode within one field,
  no dependent filters, no remote autocomplete, no "only values in use" variant for
  relations (every related object is offered, as in Django's `RelatedFieldListFilter`).
- A choice filter renders every option into the page. The search box keeps a long list
  usable, but thousands of related objects are still thousands of options. For that, use
  Django's `RelatedOnlyFieldListFilter` or search.
- Hiding `<option>`s in a search is honoured by Chromium, which the gate runs. Other
  browsers are untested and may show every option; the dropdown still works.
- `<input type="date">` and `<input type="datetime-local">` are the browser's own controls.
  Their displayed format follows the browser's locale rather than Django's, and a browser
  without them falls back to a text field that wants `YYYY-MM-DD`.
- Error-offset marking depends on the browser's parser message, which differs between
  engines and is absent in some.
- Accessibility has not been audited. The field is a real `<textarea>` and the highlight
  layer is `aria-hidden`, but no assistive-technology testing has been done.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for feature candidates and
[ARCHITECTURE.md](ARCHITECTURE.md) for the proposed structure and incremental implementation slices.

## License

MIT, see [LICENSE](LICENSE).
