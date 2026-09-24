# Architecture proposal

Status: architecture direction accepted by the user, including the independent `admin.button` API with `changelist_buttons`, `changeform_buttons` and `row_buttons`, and the simpler Fabriq-style JSON widget direction. Both are now implemented; the JSON simplification below describes shipped behavior. The range filters of wave 3 and the choice filters after them are implemented too, and the Filters section below describes what ships rather than a proposal. Local decomposition remains revisable; backend/REPL questions below remain open. This is not a description of shipped features or authorization to implement the entire roadmap. Approval reference: Discord message 1551266173528703077.

Scope: django-extensions-admin, the reusable library. The user's upcoming application is its first consumer, not the subject of this architecture. Its repository and requirements are not yet supplied.

Read [PHILOSOPHY.md](PHILOSOPHY.md) first. This plan applies the prepared architecture-foundation v1: recognizable responsibilities, framework-native roles, small useful slices, economical evidence and removable integrations. Local decomposition may change when implementation reveals a simpler shape.

## Current baseline

Inspected checkout: existing first-slice worktree, branch feat/first-slice. The baseline contains buttons, a JSON widget, demo and tests; implementation files are still uncommitted. Preserve this work before any subsequent reorganization. This planning pass changes documentation only and does not move or clean up the checkout.

```text
src/django_extensions_admin/
├── __init__.py
├── apps.py
├── conf.py
├── buttons/
│   ├── decorators.py
│   ├── mixins.py
│   └── views.py
├── jsonwidget/
│   ├── widgets.py
│   └── readonly.py
├── templates/django_extensions_admin/
└── static/django_extensions_admin/
demo/
tests/
browser_tests/
scripts/
```

Keep the working slices, but simplify mechanisms that exceed the product need. Buttons have an independent, Django-like API rather than being registered as bulk actions. The standalone Python formatter was a real implementation, not a required architectural boundary; it has since been removed, as described below.

## Proposed shape as features arrive

`+` means proposed, not present. Do not create empty future directories or move working modules solely to match this picture.

```text
src/django_extensions_admin/
├── __init__.py                 small public surface; no eager optional integrations
├── admin.py                  + our button API namespace, not a proxy for django.contrib.admin
├── apps.py                     opt-in setup; no worker/REPL startup
├── conf.py                     defaults and validation, not a configuration framework
├── buttons/                    separately registered, Django-like buttons
│   ├── decorators.py
│   ├── mixins.py
│   └── views.py
├── jsonwidget/                 simplified: stdlib rendering, no custom parser
│   ├── widgets.py              thin Python widget and initial rendering
│   └── readonly.py             escaped readonly output and its own stylesheet opt-in
├── filters/                    range and choice filters using list_filter
│   ├── query.py                what a sidebar filter form carries from the changelist
│   ├── ranges.py               date/numeric filtering: three list_filter classes
│   └── choices.py              one-value dropdown and same-field multiple choice
├── commands/                 + allowlisted management-command UI
│   ├── registry.py           + explicit command definitions, forms, permissions
│   ├── forms.py              + shared Django form behavior if actually needed
│   ├── admin.py              + opt-in AdminSite URL/context integration
│   ├── views.py              + validation, enqueue and protected result views
│   └── tasks.py              + Django Task invoking a registered command
├── branding.py               + small validated palette/branding configuration
├── templates/django_extensions_admin/
│   ├── buttons/
│   ├── filters/                range and choice bodies inside the stock <details> shell
│   ├── commands/            +
│   └── branding/            + narrow additive blocks
└── static/django_extensions_admin/
    ├── buttons.css
    ├── json-widget.css
    ├── json-widget.js
    ├── filters.css            sidebar fit for the filter forms; each works without it
    ├── choice-filters.js      search over already-rendered options; optional
    └── branding.css         + optional scoped/theme-variable overrides

demo/                          ordinary Django consumer with generated data
tests/                         behavior tests, grouped as features grow
browser_tests/                 consequential UI journeys only
docs/decisions/                specific unresolved/accepted trade-offs
scripts/                       existing verify/demo entry points
PHILOSOPHY.md                   accepted product direction
ARCHITECTURE.md                 this revisable proposal
ROADMAP.md                      feature candidates and next slices
```

Python package markers omitted. REPL remains a desired feature, but its transport/session design needs a spike before adding a shell package. Advanced query search likewise has no speculative parser or empty package yet.

## Boundaries and native contracts

### Buttons

Accepted correction: native-looking does not mean sharing the bulk-action registration system. Buttons use their own decorator and placement lists; neither decorating nor placing a button adds it to ModelAdmin.actions. Existing Django actions remain untouched. Reuse Django conventions (description, permission hooks, message_user, HttpResponse), not a hidden bridge between two registries.

Proposed spelling: `from django_extensions_admin import admin` exposes our `admin.button` and `admin.ButtonsMixin`; import ModelAdmin/register from django.contrib.admin normally. This is a small namespace for our API, not monkey-patching or a mirror/proxy of Django's entire admin module. A direct `button` import can remain available.

Proposed ModelAdmin options: `changelist_buttons` for the list toolbar, `changeform_buttons` for the existing-object change form, and `row_buttons` for list rows. Names follow Django's changelist/changeform vocabulary. The same object handler may appear in both changeform_buttons and row_buttons; separate handlers allow different behavior at each location. Placement/order is declared in these lists rather than duplicated in decorator position flags.

Initial callback proposal: list-level operations receive `(self, request)`; existing-object and row operations receive `(self, request, obj)`. Changeform object buttons are not automatically shown on the add form. If a later button needs selected/filtered querysets, introduce that scope explicitly rather than deriving it from checkbox state or silently treating an empty selection as all objects. Selection-driven bulk work can continue using normal Django actions. Preserve endpoint permission enforcement, POST/CSRF, authorized object lookup, intermediate responses, list state and correct form ownership with list_editable. Exact syntax remains proposed, not implemented.

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

Keep command URLs opt-in through a narrow AdminSite integration; JSON/buttons/filters do not require a custom AdminSite. Background imports must not make Django 5.2 or widget-only installations require task packages. Native 6.0 first. The spike ran the 5.2 backport (`django-tasks-db[compat]`) with identical behaviour behind one import switch; the runner slice must still test 5.2 before claiming support there.

Result authorization: bind each run to the initiating actor and the correct task/backend. A task ID alone is not authority. The spike found no actor metadata in either backend, so the first runner uses a small signed reference (result ID, alias, initiating user) checked together with the command permission. Showing runs to other admins or listing them would need minimal metadata persistence, which is a product decision. Do not smuggle in a full run-history model. Logs/results need bounded size, output sanitization and capability-aware availability. Dispatch follows transaction commit when needed; retries are explicit for non-idempotent commands.

### Branding and REPL

Branding changes documented CSS variables and narrow template blocks, preserving block.super, native assets, DOM hooks and light/dark/auto. Native AdminSite title/header settings remain authoritative. Component styles stay namespaced. Turning branding off must leave the functional features working; no global reset or broad input/button rules.

REPL is a separate explicit opt-in with feature-local dependencies and a separately authorized route. Its exploratory task must resolve authentication, session/process lifecycle, expiry, resource limits and deployment transport, and evaluate Ghostty frontend feasibility. It is arbitrary Python execution with application privileges, not a sandbox. Do not force WebSockets/ASGI tooling onto the rest of the package before that decision.

## Dependency and removal rules

- Each feature depends on Django, not on neighboring features. Share a helper only when a concrete shared responsibility appears.
- Commands use Django Tasks; backend packages are optional application-selected integrations. Django tasks are not our replacement for a queue runtime.
- Core library features need no application data models/migrations. Queue backend tables belong to the selected backend. Any new library persistence requires a justified change to this plan.
- No repository-wide services/selectors/repositories hierarchy, compulsory MegaModelAdmin, generic operation DSL or utils dumping ground.
- Removal: remove widget/filter declarations, button presentation bindings, or command routes/configuration. Business actions, JSONField data and management commands stay usable in Django. Drain pending work and handle retained results before removing execution integrations. Native replacements get a documented transition, not permanent compatibility machinery.

## First implementation waves

Queue only one bounded outcome at a time; these are proposed tasks, not dispatched workers.

1. **Independent Django-like buttons.** Implement the separate button decorator and changelist/changeform/row placement lists. Prove buttons never leak into the action dropdown, native actions stay intact, object handlers can be reused in two positions, and permission/CSRF/intermediate responses/list_editable work. No backend or branding changes.
   **Separate bounded cleanup before the consumer pilot:** done - JSON rendering was simplified against the Fabriq UX reference, removing the custom Python parser and the duplicated JS grammar rather than relocating them, closing the readonly-only asset gap, and restating the fidelity guarantee honestly in the README.
2. **First consumer pilot.** Once the user supplies the application, install a local wheel and integrate one useful button and JSON field. Record integration friction; do not pull application business logic into the library. This feedback may reorder subsequent work.
3. **Range filters.** Done, ahead of the consumer pilot: `DateRangeFilter`, `DateTimeRangeFilter` and `NumericRangeFilter` through list_filter, composed with search, ordering, the other filters and the admin's own queryset. Valid, partial, reversed and unreadable input and the active-timezone day boundaries are covered by behavior tests on Django 5.2 and 6.0, plus browser journeys for layout, narrow/dark and the missing-stylesheet fallback. Choice filters followed as the next small slice and are done too: `ChoiceFilter` and `MultipleChoiceFilter`, with same-field OR as repeated Django parameters, M2M de-duplication, tampered-value handling, facets and optional option search. They are covered by behavior tests on Django 5.2 and 6.0 and by browser journeys for the dropdown, OR, composition, Clear, no-JS, search and narrow/dark layout.
4. **Task-backend spike.** Done: a harmless allowed command, failure, JSON payloads, transaction timing, shutdown and result access ran on real django-tasks-db workers (Django 5.2/6.0/6.1) and a real Celery worker. The decision note records tested versions, observed behaviour and the first-runner boundary. No backend abstraction was added.
5. **Minimal command runner.** Explicit registry, argument form, permitted launch and basic authorized status/output using the validated backend. Done when allowed and denied runs and worker failure are exercised. No persisted history dashboard, auto-retry policy or generic form builder.
6. **Restrained branding.** Palette/logo/title with on/off checks for stock widgets, our editor, light/dark/auto and project overrides. No markup redesign.
7. **REPL spike, then a separate implementation decision.** Validate Ghostty transport and process lifecycle before offering a production-facing shell. Advanced query search remains a later bounded design task.

For evolutionary work, use behavior-driven red/green/refactor and retain the existing repository gate. Add tests for plausible failure modes, not quotas or every helper. Use a few browser journeys for selection, layout, fallback and form ownership; do not replay the full rule matrix at every layer.

## Philosophy fit

Need: repeated admin friction without replacing Django. Smallest API: ordinary ModelAdmin declarations, widgets, filters, forms and Tasks. Independence: optional modules without cross-feature adoption. Safety: explicit scope/authorization/activation, native data semantics. Exit path: remove the presentation/integration while preserving application logic and data. Scope: no new admin platform, queue or history system.

## Open before relevant implementation

- First consumer repository, its Python/Django versions, custom AdminSite/templates and existing runner.
- Confirm the proposed independent button namespace and changelist/changeform/row list names; advanced selected/filtered button scope is not required for the first slice.
- Whether command runs must be visible to admins other than the initiator, or listed (needs minimal metadata persistence).
- REPL deployment/transport and target environment.

These do not block discussing or refining the independent button slice. Do not invent the new application's architecture from this library plan.
