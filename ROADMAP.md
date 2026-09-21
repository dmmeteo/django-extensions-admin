# Roadmap

Before selecting or expanding any item, apply the **Philosophy fit** check in
[PHILOSOPHY.md](PHILOSOPHY.md). These candidates do not override the project principles.

This first slice deliberately ships a few things well rather than ten things thinly:
**buttons**, the **JSON field editor** and **date/numeric range filters**. The items below
are wanted, are not abandoned, and are simply not in this release.

## Next

The proposed module boundaries and bounded implementation waves are in
[ARCHITECTURE.md](ARCHITECTURE.md). They are planning, not implemented features or
a dispatched batch. Independent Django-like buttons, the simplified JSON widget and the
range filters are done and are described in the [README](README.md). Range filters landed
ahead of the consumer pilot, which remains the next outcome and may still reorder the rest.

- **First consumer pilot** - install the wheel in the user's application, integrate one
  button and one JSON field, and record the integration friction. This feedback may reorder
  everything below.
- **Execution and styling design** - apply the accepted requirements and evaluate the native Django Tasks backend approach in [actions-and-task-execution.md](docs/decisions/actions-and-task-execution.md). Backend integrations remain unverified; customization must preserve stock-admin-dependent widgets and extensions.

- **Choice filters** - searchable, dropdown and multi-value choices, the slice after the
  shipped date and numeric ranges. Same rule: `list_filter` entries, no query engine.
- **Advanced query search** - a richer changelist search alongside the basic filters.

## After that

- **Operational tools** - launching explicitly allow-listed management commands, and
  triggering background jobs through a task runner the project already has. Execution
  matters more than a jobs dashboard. No implicit authorisation of arbitrary commands, and
  nothing that implies sandboxing.
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
