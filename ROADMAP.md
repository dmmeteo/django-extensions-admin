# Roadmap

One checklist of outcomes. A checked item is implemented and covered by the repository gate;
it is not a claim that anything is released. Before selecting or expanding any item, apply the
**Philosophy fit** check in [PHILOSOPHY.md](PHILOSOPHY.md). Candidates and unchecked items do
not override the project principles, and none of them is permission to start work until it is
selected.

## First slice

This first slice deliberately ships a few things well rather than ten things thinly. Usage
and limits are in the [docs](docs/installation.md) pages; boundaries and reasons are in
[ARCHITECTURE.md](ARCHITECTURE.md).

- [x] **Buttons.** An independent `button` decorator with `changelist_buttons`,
  `changeform_buttons` and `row_buttons`. Buttons never enter the action dropdown.
- [x] **JSON field editor.** Simplified against the Fabriq reference: stdlib rendering, a
  whitespace-only Format button and its own read-only asset opt-in.
- [x] **Date and numeric range filters.** Behaviour tests on Django 5.2 and 6.0, browser
  journeys for layout, narrow and dark themes, and the missing-stylesheet fallback.
- [x] **Choice filters.** A one-value dropdown and a same-field multiple choice. Behaviour
  tests on Django 5.2 and 6.0, browser journeys for the dropdown, OR, composition, Clear,
  no-JS, search, and narrow and dark layouts.
- [x] **Minimal command runner.** An explicit registry, Django forms and permissions, and
  initiator-only status and output on django-tasks-db, on Django 5.2 and 6.0 with real
  `db_worker` journeys. It followed a task-backend spike on real workers
  ([decision note](docs/decisions/actions-and-task-execution.md)). Not built: a persisted
  history dashboard, an auto-retry policy or a generic form builder.
- [x] **Restrained branding.** An optional logo and an allowlisted palette of Django's own
  colour variables, adopted by extending one template and tested on the stock admin only.
  Title text stays the `AdminSite`'s. Not built: fonts, layout options, presets, per-user or
  per-site themes, or free-form CSS.

Both filter slices landed ahead of the consumer pilot. The pilot remains the next outcome and
may still reorder everything below it.

## Selective installation, tools panel, REPL and environment indicator

Owner-directed outcome (2026-10-30): one repository and one public name, where a project installs
only the features it chooses. Its task checklist:

- [x] **Feature distributions.** The core `django-extensions-admin` depends on Django alone; each
  feature is a distribution under `packages/` with its own source root, selected by an extra
  (`[buttons]`, `[jsonwidget]`, `[filters]`, `[commands]`, `[branding]`, `[environment]`,
  `[repl]`, `[all]`). Import paths, template names and static paths are unchanged.
- [x] **Isolation proof.** The gate installs bare, buttons, REPL, buttons+REPL, environment and all
  from the built wheels and proves unselected modules, files and dependencies are absent, then
  adds and removes features without touching the others' files. Every sdist installs.
- [x] **Environment indicator.** A name enables it; top by default, a 5 px red accent line and a
  readable badge; dict overrides for colour, position and height, validated at the boundary.
- [x] **Shared tools panel.** A tool-neutral, resizable side panel with a Django-style icon button,
  right by default and left by setting, drag and keyboard resizing, persisted width and viewport
  clamping.
- [x] **Global header stays native.** Owner correction (2026-10-30): the panel starts below Django's
  header, which keeps its full width, height and wrapping on both sides, through resizing, at
  narrow widths and in both themes; only the page below the header makes room. Browser journeys
  assert the header geometry closed, open, dragged, clamped, reloaded and navigated.
- [x] **Resizable on small screens.** Acceptance correction (2026-10-30): below 760 px the panel
  overlays the page but keeps its handle, touch and pointer drag and keyboard resizing (240 px to the
  viewport minus 32 px). Browser journeys at 375 and 390 px, both sides, prove width deltas, header
  geometry, grid agreement, persistence and a viewport change.
- [x] **REPL in the panel.** The PTY-backed Django shell, default off, active staff superusers only on
  HTTP and WebSocket, one session per user that survives navigation and reload, exact terminal grid
  agreement with the server (the resize race fixed and covered), one ASGI process.
- [x] **Docs and media.** Reference pages for the new features, a short README with a GIF, and a
  REPL screenshot, captured from real journeys and checked against the UI files they show.
- [ ] **Independent review and owner sign-off.** High-risk change (packaging, gate, arbitrary code
  execution): it needs an independent review and the owner's explicit sign-off before `main`.

## Open outcomes

- [ ] **First release (0.1.0).** Not on PyPI until an upload succeeds. Publishing is the
  owner's step ([RELEASING.md](RELEASING.md)).
  - [x] The wheel and sdist are built, content-checked, metadata-validated and clean-installed
    by the gate. The lanes cover Python 3.12 to 3.14.
  - [ ] The release commit switches the "not yet published" notes to the PyPI install and the
    links to `main` ([RELEASING.md](RELEASING.md) step 3), and the gate passes on it.
  - [ ] The owner uploads exactly the eighteen gate-checked files to PyPI, features first.
  - [ ] Tag `v0.1.0`, create the GitHub release and check a fresh install from PyPI.
- [ ] **First consumer pilot.** The next evidence-producing outcome. The first known consumer
  (Python 3.14, Django 5.2) has no model, JSON field or button suited to it yet, so the pilot
  waits for one. Nothing is invented in this repository to stand in for it.
  - [ ] Install the built wheel in the consumer application.
  - [ ] Integrate one useful button and one JSON field. Application business logic stays in
    the application.
  - [ ] Record the integration friction. This feedback may reorder everything below.

  Open before the pilot: the consumer's custom `AdminSite` and templates, its existing task
  runner, and a model, JSON field or button suited to the pilot. Do not invent the consumer's
  architecture from this library's plans.

## Deferred decisions

- **Project and package name.** FUTURE PENDING. Once the project is ready, the owner intends to ask
  the holder of a preferred name whether it can be transferred, and to rename only with that
  permission. Until then the name stays `django-extensions-admin`; nothing has been requested,
  reserved or published.

Each needs an explicit product decision before any work starts.

- **Command runner visibility.** Runs are visible to their initiator only, and there is no
  list. Showing a run to other admins, or listing runs, needs minimal metadata persistence.
- **Celery adapter.** Deferred until django-tasks-celery matures; the reasons are in the
  [decision note](docs/decisions/actions-and-task-execution.md).
- **Branding beyond the stock admin.** Naming a third-party admin integration as compatible
  needs its own test first. Per-site branding waits for a consumer that needs it.

## Candidates

Wanted and not abandoned, but not in the first release and not yet selected.

- [ ] **More tools in the panel.** An AI assistant tool is backlog only: nothing of it exists, it is
  not offered in the panel, and it would need its own product decision on credentials, data
  exposure and authorization before any work. Other panel tools wait for a concrete need.
- [ ] **REPL across several server processes.** Sessions live in one ASGI process today. Spreading
  them needs a session-placement design, not a lock change.

- [ ] **Advanced query search.** A richer changelist search alongside the basic filters. A later
  bounded design task, with no speculative parser or empty package before then.
- [ ] **Operational tools, after that.** Beyond the command runner: triggering background jobs
  through a task runner the project already has. Execution matters more than a jobs
  dashboard. No implicit authorisation of arbitrary commands, and nothing that implies
  sandboxing.

## Considered, uncommitted

- A better view over Django's own `LogEntry`. This is not model versioning, a business
  audit trail or automatic snapshots.
- Import/export and bulk edits.
- Persisted history of button runs.

## Deliberately out of scope

An action-form framework, changelist upload panels, a custom page builder, dependent
selects, enhanced inlines, saved filter presets, schema-driven JSON forms, a JSON tree UI,
an own task queue, an audit/versioning backend, and any admin redesign.

A browser REPL is not part of the core: it is the optional `[repl]` feature distribution, off
until a setting enables it. An operating-system shell, a SQL console and a second command runner
inside the panel are out of scope.

Each feature stays independent and additive. Nothing here should ever require a mandatory
base class or replace the stock admin.
