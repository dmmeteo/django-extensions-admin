# Roadmap

Before selecting or expanding any item, apply the **Philosophy fit** check in
[PHILOSOPHY.md](PHILOSOPHY.md). These candidates do not override the project principles.

This first slice deliberately ships a few things well rather than ten things thinly:
**buttons**, the **JSON field editor**, **date/numeric range filters**, **choice
filters**, a minimal, opt-in **management-command runner** and opt-in **restrained
branding**. The items below
are wanted, are not abandoned, and are simply not in this release.

## Next

The proposed module boundaries and bounded implementation waves are in
[ARCHITECTURE.md](ARCHITECTURE.md). They are planning, not implemented features or
a dispatched batch. Independent Django-like buttons, the simplified JSON widget, the
range filters, the choice filters, the minimal command runner and restrained branding are
done and are described in the [README](README.md).
Both filter slices landed ahead of the consumer pilot, which remains the next outcome and
may still reorder the rest.

- **First consumer pilot** - install the wheel in the user's application, integrate one
  button and one JSON field, and record the integration friction. This feedback may reorder
  everything below.
- **Command runner, next steps** - the minimal runner ships. It covers registered
  commands, Django forms and permissions, django-tasks-db on Django 5.2 and 6.0, and
  initiator-only status and output. Visibility to other admins, or a list of runs, would
  need minimal metadata persistence. That stays a separate product decision, taken only if
  a consumer needs it. The Celery adapter stays deferred
  ([decision note](docs/decisions/actions-and-task-execution.md)).
- **Branding, next steps** - the logo and allowlisted palette ship, tested on the stock
  admin only. Naming a third-party admin integration as compatible needs its own test
  first. Per-site branding waits for a consumer that needs it.

- **Advanced query search** - a richer changelist search alongside the basic filters.

## After that

- **Operational tools** - beyond the command runner: triggering background jobs through
  a task runner the project already has. Execution matters more than a jobs
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

Each feature stays independent and additive. Nothing here should ever require a mandatory
base class or replace the stock admin.
