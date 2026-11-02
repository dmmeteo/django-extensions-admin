# Architecture

Status: architecture direction accepted by the user (approval reference: Discord message 1551266173528703077), including the independent `admin.button` API with `changelist_buttons`, `changeform_buttons` and `row_buttons`, and the simpler Fabriq-style JSON widget direction. The buttons, JSON, filters, management commands and branding sections describe shipped behavior and the reasons behind it. Local decomposition remains revisable. Owner direction of 2026-10-30 supersedes the former exclusion of a REPL companion: one repository ships the core and independently installable feature distributions, including an optional REPL in a shared tools panel and an environment indicator; see Packaging, Tools panel, REPL and Environment below. Coding-agent chat is not part of it. Version 0.1.0 is prepared for a first release but not published. This document is not authorization to implement the roadmap; [ROADMAP.md](ROADMAP.md) tracks status and open outcomes.

Scope: django-extensions-admin, the reusable library. The user's application is its first known consumer (Python 3.14, Django 5.2), not the subject of this architecture. It has no model, JSON field or button suited to a pilot yet.

Read [PHILOSOPHY.md](PHILOSOPHY.md) first. This plan applies the prepared architecture-foundation v1: recognizable responsibilities, framework-native roles, small useful slices, economical evidence and removable integrations. Local decomposition may change when implementation reveals a simpler shape.

## Module map

Do not create empty future directories or move working modules solely to match this picture.

```text
src/django_extensions_admin/              core distribution: django-extensions-admin (Django only)
├── __init__.py                 lazy public names; a missing feature names its extra
├── admin.py                    our button/filter namespace, lazy, no side effects
├── apps.py                     startup hooks of installed features; W001/W002 setting checks
└── conf.py                     ADMIN_EXTENSIONS defaults for every feature
packages/<feature>/                       one distribution each: pyproject, README, LICENSE, src/
├── buttons/src/django_extensions_admin/  buttons/, templates/.../buttons/, change_list/form, buttons.css
├── jsonwidget/src/...                    jsonwidget/ (widgets, readonly, default), json-widget.css/js
├── filters/src/...                       filters/ (query, ranges, choices), templates, css, js
├── commands/src/...                      commands/ (registry, backend, checks, views, tasks), pages, css
├── branding/src/...                      branding.py, templatetags/admin_ext_branding.py, template, css
├── environment/src/.../environment/      app: indicator.py, admin/base_site.html layer, css
├── panel/src/.../panel/                  app: Tool registry, admin/base_site.html layer, panel.js/css
└── repl/src/.../repl/                    app: conf, access, sessions, consumers, views, routing,
                                          tool template, repl.js/css, vendored ghostty-web 0.4.0

demo/                          ordinary Django consumer with generated data, ASGI for the REPL
tests/                         behavior tests, run against the installed wheels
browser_tests/                 consequential UI journeys; panel/REPL ones against real daphne
docs/                          user reference, one page per feature; docs/media + manifest
docs/adr/index.md              index of the decision records
docs/decisions/                specific unresolved/accepted trade-offs
docker/ci.Dockerfile           capped runtime for scripts/verify.sh
scripts/                       verify, demo, vendor-ghostty; scripts/ci/ probes and checks
spikes/task_backends/          disposable evidence harness for the decision note
AGENTS.md                      agent entry point and working rules
PHILOSOPHY.md                   accepted product direction
ARCHITECTURE.md                 this document: boundaries and their reasons
ROADMAP.md                      outcome checklist, deferred decisions and candidates
```

Python package markers omitted. Advanced query search has no speculative parser or empty package yet, and there is no AI tool package.

## Boundaries and native contracts

### Buttons

Accepted correction: native-looking does not mean sharing the bulk-action registration system. Buttons use their own decorator and placement lists; neither decorating nor placing a button adds it to ModelAdmin.actions. Existing Django actions remain untouched. Reuse Django conventions (description, permission hooks, message_user, HttpResponse), not a hidden bridge between two registries.

Spelling: `from django_extensions_admin import admin` exposes our `admin.button` and `admin.ButtonsMixin`; import ModelAdmin/register from django.contrib.admin normally. This is a small namespace for our API, not monkey-patching or a mirror/proxy of Django's entire admin module. A direct `button` import can remain available.

ModelAdmin options: `changelist_buttons` for the list toolbar, `changeform_buttons` for the existing-object change form, and `row_buttons` for list rows. Names follow Django's changelist/changeform vocabulary. The same object handler may appear in both changeform_buttons and row_buttons; separate handlers allow different behavior at each location. Placement/order is declared in these lists rather than duplicated in decorator position flags.

Callbacks: list-level operations receive `(self, request)`; existing-object and row operations receive `(self, request, obj)`. Changeform object buttons are not automatically shown on the add form. If a later button needs selected/filtered querysets, introduce that scope explicitly rather than deriving it from checkbox state or silently treating an empty selection as all objects. Selection-driven bulk work can continue using normal Django actions. Preserve endpoint permission enforcement, POST/CSRF, authorized object lookup, intermediate responses, list state and correct form ownership with list_editable.

### JSON

The JSON widget changes presentation, not model field type, validation or storage. Implemented as a thin `AdminTextareaWidget` using `json.loads`/`json.dumps` in `format_value`, plus vanilla JS for highlighting, autosize, validation and an explicit reformat - the Fabriq reference shape. The earlier tokenizer and recursive pretty-printer in `jsonwidget/formatter.py` were removed rather than relocated.

Why that is not a loss: Django's `forms.JSONField.bound_data()` parses submitted text and `prepare_value()` re-serialises it, so every string reaching `format_value` has already been through the same stdlib round trip. The one string that has not - `InvalidJSONInput`, kept after failed validation - is deliberately returned untouched, so malformed submitted input still survives redisplay byte for byte. Native JSONField storage semantics are unchanged; README states the boundary between rendering, the browser's Format button and a save.

Browser formatting must not silently change large integers, and this is the one place where the risk is real: the text has not reached the server yet. `JSON.parse`/`JSON.stringify` turns 9007199254740993 into 9007199254740992 and 1.0E2 into 100, so the script validates with the native parser and then re-indents whitespace only, copying every literal verbatim. That re-indenter carries no grammar of its own - it runs only on text `JSON.parse` accepted - so no full JSON grammar is duplicated between Python and JS. Highlighting on both sides is one token regex, escaped, degrading to plain text on input it does not recognise.

Readonly rendering is server-side escaped `<pre>` markup with the same token regex, and carries its own asset opt-in (`JSONReadonlyMixin`, a plain Django `class Media`), so a readonly-only admin depends on neither an editable widget nor the buttons mixin; without the stylesheet the text is still readable. XSS, missing-CSS, undo/selection, no-JS and oversized-input checks stay focused on observable behavior.

### Filters

Filters plug into ModelAdmin.list_filter and the authorized queryset. No generic query engine. Date boundaries/timezones and numeric input get focused behavior checks, not a new expression language.

Range filters are implemented in `filters/ranges.py`: three `FieldListFilter` subclasses over one private base, plus a template and `filters.css`. Nothing is registered with `FieldListFilter.register`, so installing the app still changes no existing admin, and there is no mixin, setting or custom AdminSite. Each filter owns exactly two query parameters, `<field_path>__range__gte` and `__lte`, declared in `expected_parameters()` so the changelist hands them over instead of treating them as raw lookups.

Bounds are parsed by Django form fields, not by our own parsing: `forms.DateField` / `forms.DateTimeField` for date-like columns - which already route through `from_current_timezone()` - and the model field's own `formfield()` for numbers, so precision, limits and the input step come from the column. A date range over a DateTimeField is `__gte` local midnight to `__lt` the next local midnight, rather than an inclusive bound on a chosen last instant. Timezone correctness is a behavior check against Django's own `__date` lookup, not an assertion about our arithmetic.

Input the filter cannot read returns `queryset.none()` with the error rendered in the sidebar. That is deliberate: the filter runs after `ModelAdmin.get_queryset()`, so silently ignoring a bad bound would widen what is shown relative to what was asked for. Nothing raises, and the changelist's own `e=1` error path stays for Django's cases.

Presentation stays inside the stock `<details data-filter-title>` shell; only the body is a GET form carrying the rest of the query string as hidden inputs. No JavaScript. The stylesheet is linked from the filter template because a ListFilter has no media hook - the changelist collects media from the ModelAdmin, not from its filters - and the form is usable without it.

Choice filters are implemented in `filters/choices.py`: `ChoiceFilter` (one value, a `<select>`) and `MultipleChoiceFilter` (several values of one field ORed, a checkbox list in the stock `<ul>`/`li.selected` markup) over one private base. The field category is resolved once: relations take their options from `field.get_choices()` in the related admin's ordering, fields with choices from `flatchoices`, and plain char/integer/decimal/UUID columns from the admin's own distinct values, as `AllValuesFieldListFilter` does. Any other field raises `ImproperlyConfigured`. Nothing is registered.

Parameters are Django's own for each category (`<path>__<pk>__exact`, `<path>__exact`, `<path>`, plus `<path>__isnull` for the empty choice), and several values are a repeated key. Django 5.0+ already hands filters list-valued params and ORs a repeated key in its own filters, so this needs no parsing of ours, keeps values with commas intact (unlike the documented comma-separated `__in`), and leaves bookmarks valid after a project swaps back to the stock filter. The query is one `filter()` with `__in` ORed with `__isnull`, so a multi-valued relation joins once and the changelist's own `lookup_spawns_duplicates` de-duplication applies. A dropdown has one parameter name and cannot also send `__isnull`, so `ChoiceFilter` has no empty choice rather than an invented sentinel, and it reads only the last value it is given.

Values are parsed with the lookup target's own `to_python`. One it cannot read matches nothing, an `__isnull` other than true is not reinterpreted as "not empty", and when nothing readable remains the result is `queryset.none()`. Nothing raises. A sidebar note says a value is not one of the choices, so the control never claims "All" over a filtered list. Clear deletes its exact keys through `get_query_string({key: None})`, because `remove=` matches by prefix. The carried-query rule is shared with the range filters in `filters/query.py`.

Option search is `choice-filters.js`, the only script in the filters. It is linked from the template, idempotent per form because the tag repeats per filter, and runs only on forms whose option count the server judged longer than `search_threshold`. It hides non-matching options already on the page and never changes the selection or submits anything. Without it, the forms are unchanged.

### Management commands and background work

Flow: AdminSite view -> explicit registry + Django form + permission check -> enqueue configured Django Task -> worker revalidates registered command/options -> Django call_command -> bounded result.

Commands are registered by the application; discovery is not permission to run. Forms supply typed, JSON-safe arguments. Neither raw shell strings nor arbitrary management-command names are accepted from the browser. The task and UI share the same registry/validation meaning, not duplicated business rules.

Prefer the Django Tasks interface with an explicitly selected backend alias. The application owns worker deployment, broker/database queue and retention. The backend spike chose django-tasks-db as the first supported backend and deferred django-tasks-celery 0.1.1; the evidence and failure modes are in [the decision note](docs/decisions/actions-and-task-execution.md). No custom queue, executor factory, workflow engine or silent inline fallback. Existing application Celery tasks can still be launched by ordinary application callbacks without conversion.

Keep command URLs opt-in through a narrow AdminSite integration; JSON/buttons/filters do not require a custom AdminSite. Background imports must not make Django 5.2 or widget-only installations require task packages. Native 6.0 first. The spike ran the 5.2 backport (`django-tasks-db[compat]`) with identical behaviour behind one import switch; the runner is tested on both.

Result authorization: bind each run to the initiating actor and the correct task/backend. A task ID alone is not authority. The spike found no actor metadata in either backend, so the first runner uses a small signed reference (result ID, alias, initiating user) checked together with the command permission. Showing runs to other admins or listing them would need minimal metadata persistence, which is a product decision. Do not smuggle in a full run-history model. Logs/results need bounded size, output sanitization and capability-aware availability. Dispatch follows transaction commit when needed; retries are explicit for non-idempotent commands.

As shipped (wave 5). The shape is `commands.register(name, permission=..., form=...)` in an `admin.py`, which is autodiscovered in the worker too, plus `commands.urls(site)` included ahead of `site.urls`. There is no AdminSite subclass, and nothing is routed unless it is included.
- **Payload.** It is the form's submitted values as JSON, keyed as the widgets read them (a split field as its sub-inputs). They are validated a second time before enqueue, comparing prepared values so querysets compare by keys, and again in the worker, so a model choice travels as a key.
- **Blank options.** A blank non-required field is left out of `call_command()`, so the command's argparse default applies. `False` and `0` are passed.
- **Worker checks.** The worker also rechecks the registration and the launching user: active staff, the admin boundary, plus the permission. The actor id is a string, so non-integer keys work.
- **Failures.** A failure is a truthful backend `FAILED`, raised `from None`. What is stored is only the bounded JSON summary (the exception line and bounded output), which is shown instead of the traceback; the original goes to the worker log. A non-zero `sys.exit()` is a failure, while the worker's own shutdown `SystemExit` propagates.
- **Enqueue errors.** They are reported as "may not have been queued", because django-tasks-db can store the row before `task_enqueued` raises.
- **Registration.** It must happen in a module that both processes import: `admin.py` under `AdminConfig`, or `AppConfig.ready()` under `SimpleAdminConfig`.
- **Transactions.** The launch view opts out of `ATOMIC_REQUESTS` on every database alias and refuses inside an open transaction. That is the honest consequence of dispatching on commit without persistence.
- **Imports.** Nothing outside `commands/` imports it, and the wheel depends on Django alone. Backend installation is one documented line per Django version, because django-tasks-db's `[compat]` extra pins Django below 6.0.

### Branding

Branding changes documented CSS variables and narrow template blocks, preserving block.super, native assets, DOM hooks and light/dark/auto. Native AdminSite title/header settings remain authoritative. Component styles stay namespaced. Turning branding off must leave the functional features working; no global reset or broad input/button rules.

As shipped (wave 6):
- **Adoption.** A project's own `admin/base_site.html` extends `django_extensions_admin/branding/base_site.html`. That template extends `admin/base_site.html` again, which Django's recursive `extends` resolves past the project's file to the next one down (normally the stock one). Nothing is registered, replaced or patched when the app is installed, and `ADMIN_EXTENSIONS["BRANDING"]` alone changes no page. Every AdminSite shares the one branding and keeps its own text.
- **Blocks.** Only `dark-mode-vars` (palette, after Django's variables, before `extrastyle`, and overridden by no stock template) and `branding` (logo before the stock `#site-name`), both with `block.super`. Project CSS goes in `extrastyle`, after the branding layer.
- **Palette.** Django's own variable names, from an allowlist of brand surfaces (header, breadcrumbs, captions, links, buttons), hex values only, invalid entries dropped and reported (E201-E207, W201). Variables Django's `dark_mode.css` redefines are set for light only unless `DARK_COLORS` gives a dark value; the rest apply to both themes, as in Django. The selectors are Django's own shapes, so equal-specificity project rules loaded later win. A test guards the dark-sensitive list against the installed `dark_mode.css`. Nothing is derived.
- **Logo.** A static path, never a remote or `data:` URL. It is 32 px high, bounded in width by `branding.css`, not a link and not a tab stop. It is decorative by default (`alt=""`), since the stock site name beside it is the header's accessible name; `LOGO_ALT` is for a logo that says more. A storage miss renders no logo rather than an error.
- **CSP.** The `<style>` takes Django 6.0's `csp_nonce` when the CSP middleware provides one.
- **Proof.** Unit tests show every page body (index, changelist, change form with inlines and JSON, validation errors, login, command pages) is byte-identical with and without branding apart from the one `<img>`. Browser journeys cover themes, the toggle, 375/390 px, keyboard order, project overrides and missing parts. Only the stock admin is claimed.

### Packaging

Extras cannot remove files from one wheel, so "install only what you use" is real distributions: the core and one small distribution per feature, all in this repository, each with its own source root installing into the shared `django_extensions_admin` directory. The core owns `__init__.py`; no other distribution ships a file another one ships (the gate checks this), so pip adds and removes one feature's files without touching the others'. The public entry stays one name with extras, `django-extensions-admin[buttons,repl]`, and every pin between them is exact because they are built and tested together. A prototype showed why each companion needs a real source root: hatchling `force-include` from outside the project builds an sdist that cannot build its own wheel.

Import paths, template names and static paths did not change. The core's `__init__` and `admin` resolve public names on first use, so importing the core imports no feature and a missing one fails with its extra. Features that were adopted through the core app (buttons, JSON, filters, commands, branding) keep their templates and static files under the core app's directory, so `INSTALLED_APPS = ["django_extensions_admin"]` still finds them. Features that change every admin page or bring their own checks and routes (environment, panel, REPL) are apps of their own. Tests run against the installed wheels; editable installs of the split packages are not supported, because Django finds an app's templates in one directory.

No custom installer, plugin discovery or entry points: pip extras, `INSTALLED_APPS`, URLs and settings.

### Tools panel

`django_extensions_admin.panel` is the one side panel tools open in. A tool registers a `Tool` (key, label, template, `available(request)`, static files) from its `AppConfig.ready()`; the panel renders its header button, tabs and markup only for a request some tool is available to, through an `admin/base_site.html` layer that keeps every `block.super`. `available()` decides rendering only; each tool's views authorize every request themselves.

Owner correction (2026-10-30): Django's header is the stock global header and stays full width. The panel is fixed with its top at the header's bottom edge (measured, so wrapping, branding and an indicator above it are respected, and it reaches the top once the header scrolls away), and only `#container`'s children below the header get the docking margin. Nothing touches `body`, `#container` or `#header`. Width is clamped between 360 px and the viewport minus 400 px, stored in the browser, and applied before first paint by a small head script. Below 760 px the panel overlays the page below the header and stays resizable, between 240 px and the viewport minus 32 px (owner requirement: a narrow screen never disables manual width).

### REPL

`django_extensions_admin.repl` is the PTY-backed Django shell, adapted from the separate reference REPL and integrated as a panel tool. Flow: CSRF-protected JSON views start and end a session from a server-side backend table; a Channels consumer streams bounded, offset-addressed output and accepts input and resizes; a `SessionManager` in the one ASGI process owns process trees, idle expiry and a lock file that refuses a second hosting process. It is off unless `REPL_ENABLED` is True (404 and WebSocket close 4404), and allowed only to authenticated, active, staff superusers on every HTTP request and WebSocket connection, each to their own session, with the Django session re-read every 10 seconds. The server acknowledges each resize before later input, which is the boundary the client and the browser journeys use to prove the terminal grid and the PTY agree. ghostty-web 0.4.0 `FitAddon.fit()` drops a resize within 50 ms of the previous one, so the client resizes to `proposeDimensions()` itself. Resetting or clearing a ghostty-web 0.4.0 terminal that was resized corrupts its WebAssembly memory (a later write traps out of bounds, which Chromium's headless shell turns into a renderer crash), so the client never resets a terminal: a redraw, a new session or a server-side restart of the stream builds a new terminal on a new WebAssembly instance and replays the server's retained output.

Channels is the REPL's only dependency; IPython and django-extensions are optional backends the project installs. Multi-process session placement, an OS shell, AI credentials and a second command runner are out of scope.

### Environment

`django_extensions_admin.environment` adds an accent line and a badge through its own `admin/base_site.html` layer when `ENVIRONMENT` names an environment. Only validated values reach CSS (hex colour, `top`/`bottom`, 2-12 px) in one nonce-aware `<style>`; the name is escaped text. It depends on nothing but the core.

## Dependency and removal rules

- Each feature depends on Django and the core, not on neighboring features. The REPL depends on the panel, which exists to be shared by tools. Share a helper only when a concrete shared responsibility appears.
- Runtime dependencies follow features: the core and every feature but the REPL need Django alone; the REPL needs Channels. The gate fails on any other `Requires-Dist`.
- Commands use Django Tasks; backend packages are optional application-selected integrations. Django tasks are not our replacement for a queue runtime.
- Core library features need no application data models/migrations. Queue backend tables belong to the selected backend. Any new library persistence requires a justified change to this plan.
- No repository-wide services/selectors/repositories hierarchy, compulsory MegaModelAdmin, generic operation DSL or utils dumping ground.
- Removal: remove widget/filter declarations, button presentation bindings, or command routes/configuration. Business actions, JSONField data and management commands stay usable in Django. Drain pending work and handle retained results before removing execution integrations. Native replacements get a documented transition, not permanent compatibility machinery.

## Delivery

Buttons with the JSON simplification, range and choice filters, the task-backend spike, the minimal command runner and restrained branding have shipped, followed by selective installation, the environment indicator, the tools panel and the REPL. The first consumer pilot and the first release are still open. Advanced query search remains a later bounded design task. [ROADMAP.md](ROADMAP.md) tracks these outcomes, their coverage and what each deliberately leaves out. Working rules for new work are in [AGENTS.md](AGENTS.md).

## Philosophy fit

Need: repeated admin friction without replacing Django. Smallest API: ordinary ModelAdmin declarations, widgets, filters, forms and Tasks. Independence: optional modules without cross-feature adoption. Safety: explicit scope/authorization/activation, native data semantics. Exit path: remove the presentation/integration while preserving application logic and data. Scope: no new admin platform, queue or history system.
