# Roadmap

Before selecting or expanding any item, apply the **Philosophy fit** check in
[PHILOSOPHY.md](PHILOSOPHY.md). These candidates do not override the project principles.

This first slice deliberately ships a few things well rather than ten things thinly:
**buttons**, the **JSON field editor**, **date/numeric range filters** and **choice
filters**. The items below
are wanted, are not abandoned, and are simply not in this release.

## Next

The proposed module boundaries and bounded implementation waves are in
[ARCHITECTURE.md](ARCHITECTURE.md). They are planning, not implemented features or
a dispatched batch. Independent Django-like buttons, the simplified JSON widget, the
range filters and the choice filters are done and are described in the [README](README.md).
Both filter slices landed ahead of the consumer pilot, which remains the next outcome and
may still reorder the rest.

- **First consumer pilot** - install the wheel in the user's application, integrate one
  button and one JSON field, and record the integration friction. This feedback may reorder
  everything below.
- **Command-runner decision** - the backend evaluation is done:
  [actions-and-task-execution.md](docs/decisions/actions-and-task-execution.md) selects
  django-tasks-db for the first command runner and defers the Celery adapter. The next
  decision is whether command runs must be visible to admins other than the initiator
  (which needs minimal metadata persistence). The minimal runner comes after that
  decision; it does not exist yet.
- **Styling design** - apply the accepted styling requirements in the same note;
  customization must preserve stock-admin-dependent widgets and extensions.

- **Advanced query search** - a richer changelist search alongside the basic filters.

## After that

- **Operational tools** - launching explicitly allow-listed management commands (first
  through the minimal command runner on django-tasks-db), and triggering background jobs
  through a task runner the project already has. Execution matters more than a jobs
  dashboard. No implicit authorisation of arbitrary commands, and nothing that implies
  sandboxing.
- **Light polish** - narrowly scoped optional colours, logo and title. Not a theme
  framework and not a replacement layout.

## Considered, uncommitted

- A better view over Django's own `LogEntry`. This is not model versioning, a business
  audit trail or automatic snapshots.
- Import/export and bulk edits.
- Persisted history of button runs.

## Deliberately out of scope

An action-form framework, changelist upload panels, a custom page builder, dependent
selects, enhanced inlines, saved filter presets, schema-driven JSON forms, a JSON tree UI,
an own task queue, an audit/versioning backend, and any admin redesign.

Each feature stays independent and additive. Nothing here should ever require a mandatory
base class or replace the stock admin.
