# Native actions and task execution

Status: action-native interaction is an accepted user requirement. Django Tasks is the preferred direction to evaluate for operational tools; backend adoption is a proposal, not implemented or integration-tested.

Read PHILOSOPHY.md before turning this note into an implementation packet.

## Buttons: familiar to Django users

The user requires buttons to feel like native admin actions rather than a foreign interface. Apply this to both developer API and visual/interaction design. Django actions support a ModelAdmin method `(self, request, queryset)`, `@admin.action(description=..., permissions=...)`, `message_user`, and responses/intermediate pages.[3]

User clarification supersedes the shared-action proposal: buttons need a separate `button` decorator and explicit placement lists; they must not automatically enter ModelAdmin.actions. Preserve Django-like naming, permissions, messages and confirmation styling, without coupling button and bulk-action registries. Proposed names and callback boundaries live in [ARCHITECTURE.md](../../ARCHITECTURE.md#buttons). This is a design correction, not an implemented change.

## Styling compatibility: accepted requirement

Light customization must preserve extensions that depend on stock admin styles. Django documents CSS variables for colors/fonts and additive template blocks with `block.super`, including its light/dark handling.[8]

Proposed guardrails: use documented admin CSS variables for a small palette and native AdminSite title/header settings; add a logo through a narrow branding block. Keep stock stylesheets, DOM hooks, block contents and theme switching. Namespace component CSS; avoid global resets, broad element overrides, forced dimensions, font-metric changes and `!important` escalation. Styling is optional and independently disableable; buttons and JSON must still work without the polish module.

Acceptance before claiming compatibility: compare customization on/off on stock forms, changelist actions, list_editable, inlines, autocomplete/Select2, date widgets, validation errors and our JSON overlay; exercise light/dark/auto, narrow layouts and existing project template/CSS overrides. Test representative third-party integrations before naming them supported. CSS variables reduce coupling, but cannot guarantee compatibility with every third-party stylesheet.

## Findings: Django Tasks

Django 6.0 introduces `django.tasks`, a standard task definition/enqueue/result API. It does not include a production worker/queue implementation. Built-in ImmediateBackend runs inline and DummyBackend never executes tasks.[1]

`@task`, `.enqueue(...)`, `TASKS` backend aliases and `.using(backend=...)` provide the common interface. Arguments and return values must be JSON-serializable; enqueueing work dependent on a transaction should wait for `transaction.on_commit`. Result retrieval, delayed execution and priority support depend on backend capabilities.[1][2]

- **Without Celery:** django-tasks-db supplies ORM storage and `manage.py db_worker`; its documented backend is `django_tasks_db.DatabaseBackend`. A DB-backed queue still needs a running worker and backend installation/configuration.[4]
- **With Celery:** the third-party django-tasks-celery adapter exposes `django_tasks_celery.CeleryBackend`, routing Django task enqueue calls to Celery. Its documented setup includes broker/result configuration and `CELERY_RESULT_EXTENDED=True`. PyPI reports version 0.1.1 and Django >=6.0,<7; existence is verified, reliability has not been tested here. It is not bundled with Django or established here as official Celery support.[5][6]
- **Django 5.2:** the django-tasks backport is available. Keep it an optional operational-feature dependency; the package's buttons/JSON features must remain usable without it.[1][7]

## Recommendation / Philosophy fit

Need: launch allowed management commands without blocking admin requests. Native Django primitives suffice for the dispatch contract; do not build another queue abstraction.

Smallest shape: admin form -> explicit command registry and permission checks -> module-level Django task -> Django `call_command` -> bounded structured result/output. This is a proposed implementation shape, not a tested code snippet.

Independence: configure an explicit backend alias for admin operations. Existing Celery tasks need not be rewritten. Switching the alias/backend can preserve our task body and enqueue call, but deployment, workers, capabilities, retries, result retention and queues remain backend-specific. Drain or preserve outstanding jobs on the old backend; changing a setting does not migrate pending tasks or results.

Safety: task payload contains a registered command key and validated JSON-safe arguments, not an arbitrary executable, request, QuerySet or model instance. Recheck the command allowlist in execution. Configure noninteractive commands only. Use bounded output, permission-protected results and deliberate retry/idempotency policy. Do not present ImmediateBackend as background execution or silently fall back to it for long commands; DummyBackend is test-only. Queue unavailable means a visible failure, not a success message.

Scope/proof: before selecting an adapter, exercise one allowed command and one denied request end-to-end on a real DB worker, then on a real Celery worker, with failure/result retrieval and transaction-commit tests. Verify 5.2 backport behavior separately if supported. No claim of live log streaming or portable advanced Celery workflows; basic dispatch/result is the common denominator.

## Sources

[1] https://docs.djangoproject.com/en/6.0/topics/tasks
[2] https://docs.djangoproject.com/en/6.0/ref/tasks
[3] https://docs.djangoproject.com/en/6.0/ref/contrib/admin/actions
[4] https://raw.githubusercontent.com/RealOrangeOne/django-tasks-db/master/README.md
[5] https://raw.githubusercontent.com/oliverhaas/django-tasks-celery/main/README.md
[6] https://pypi.org/pypi/django-tasks-celery/json
[7] https://github.com/RealOrangeOne/django-tasks
[8] https://raw.githubusercontent.com/django/django/stable/6.0.x/docs/ref/contrib/admin/index.txt
