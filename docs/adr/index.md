# Decision records

Choices where alternatives were weighed and the reasons are worth keeping. Open the record
that matches the task. Add a record only for a weighed, non-obvious choice, and list it here.
The records stay where they were written.

- [Native actions and task execution](../decisions/actions-and-task-execution.md). Buttons
  stay separate from Django's bulk actions, and branding keeps to Django's variables and
  blocks. The command runner uses Django Tasks with django-tasks-db. The Celery adapter is
  deferred, and results use a signed initiator-only reference instead of a run model. Based
  on the 2026-09-24 backend spike with real workers.
- [Selective installation, the tools panel and the REPL](../decisions/selective-installation.md).
  Each feature is its own distribution under `packages/`, selected by an extra of the core, with
  unchanged import, template and static paths. The REPL joins as an opt-in tool in a shared panel
  that keeps Django's header full width. Based on the 2026-10-30 packaging prototype.
