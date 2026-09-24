# Native actions and task execution

Status: action-native interaction is an accepted user requirement. Django Tasks is the chosen direction for operational tools. The backend spike (2026-09-24) exercised real workers and selected django-tasks-db for the first command runner. The runner now ships (`django_extensions_admin.commands`, README "Management commands") within the boundary below. Runs are visible to their initiator only, and there is no run model.

Read PHILOSOPHY.md before turning this note into an implementation packet.

## Buttons: familiar to Django users

The user requires buttons to feel like native admin actions rather than a foreign interface. Apply this to both developer API and visual/interaction design. Django actions support a ModelAdmin method `(self, request, queryset)`, `@admin.action(description=..., permissions=...)`, `message_user`, and responses/intermediate pages.[3]

User clarification supersedes the shared-action proposal: buttons need a separate `button` decorator and explicit placement lists; they must not automatically enter ModelAdmin.actions. Preserve Django-like naming, permissions, messages and confirmation styling, without coupling button and bulk-action registries. Proposed names and callback boundaries live in [ARCHITECTURE.md](../../ARCHITECTURE.md#buttons). This is a design correction, not an implemented change.

## Styling compatibility: accepted requirement

*Shipped as restrained branding (README "Branding", ARCHITECTURE "Branding"). The on/off comparison below is covered on the stock admin for Django 5.2 and 6.0. No third-party integration has been tested, so none is named as supported.*

Light customization must preserve extensions that depend on stock admin styles. Django documents CSS variables for colors/fonts and additive template blocks with `block.super`, including its light/dark handling.[8]

Proposed guardrails: use documented admin CSS variables for a small palette and native AdminSite title/header settings; add a logo through a narrow branding block. Keep stock stylesheets, DOM hooks, block contents and theme switching. Namespace component CSS; avoid global resets, broad element overrides, forced dimensions, font-metric changes and `!important` escalation. Styling is optional and independently disableable; buttons and JSON must still work without the polish module.

Acceptance before claiming compatibility: compare customization on/off on stock forms, changelist actions, list_editable, inlines, autocomplete/Select2, date widgets, validation errors and our JSON overlay; exercise light/dark/auto, narrow layouts and existing project template/CSS overrides. Test representative third-party integrations before naming them supported. CSS variables reduce coupling, but cannot guarantee compatibility with every third-party stylesheet.

## Findings: Django Tasks

Django 6.0 introduces `django.tasks`, a standard task definition/enqueue/result API without a worker. Built-in ImmediateBackend runs inline in the caller and DummyBackend never executes tasks. Django's own default `TASKS` setting is ImmediateBackend (*source*: `global_settings.TASKS`), so an unconfigured project runs "background" work inside the request.[1][2]

The backend spike on 2026-09-24 exercised this contract through **real, separately started workers and durable stores** with a disposable harness, [spikes/task_backends](../../spikes/task_backends/README.md). Statements below are *observed* (reproduced by the harness) unless marked *source* or *docs* (read, not exercised).

### Tested versions

| Lane | Django | Tasks API | Backend | Store / broker |
|---|---|---|---|---|
| 6.0 native | 6.0.8 | `django.tasks` | django-tasks-db 0.13.0 | PostgreSQL 16 container; SQLite file |
| 5.2 backport | 5.2.17 | `django_tasks` 0.12.0 via `django-tasks-db[compat]` | django-tasks-db 0.13.0 | PostgreSQL 16 container; SQLite file |
| 6.1 (observation) | 6.1.1 | `django.tasks` | django-tasks-db 0.13.0 | PostgreSQL 16 container |
| Celery | 6.0.8 | `django.tasks` | django-tasks-celery 0.1.1, Celery 5.6.3, kombu 5.6.2, redis-py 8.1.0 | Redis 7 container; PostgreSQL 16 for app data |

All lanes used Python 3.13.13 and psycopg 3.3.6. Each worker was its own process (`db_worker`, or `celery worker` prefork with concurrency 1), and every result was read back by a third process that neither enqueued nor ran the task. The package itself gained no dependency.

### Observed behaviour

The five django-tasks-db runs (6.0/5.2/6.1 on PostgreSQL, 6.0/5.2 on SQLite) produced identical outcomes, except for the 5.2 module and exception paths.

| Concern | django-tasks-db | django-tasks-celery 0.1.1 |
|---|---|---|
| Process separation | Task PID = `db_worker` PID ≠ enqueuer and reader PIDs | Task PID = prefork child of the worker ≠ enqueuer and reader PIDs |
| Enqueue with no worker running | Stays `READY` after the enqueuer exits; runs when a worker starts | Same (message waits in Redis) |
| Capability flags | `supports_get_result`, `defer`, `priority`, `async_task` all true | All true; `supports_get_result` is computed and false when the Celery result backend is disabled |
| Status seen by another process | `READY` → `RUNNING` → `SUCCESSFUL`, with enqueued/started/finished times | `READY` → `SUCCESSFUL`: no `RUNNING` by default, and `enqueued_at`/`started_at` are always `None` |
| Task failure | `FAILED`, `errors[0]` has the exception path and traceback, `return_value` raises | Same |
| Unknown or malformed result ID | `TaskResultDoesNotExist` | Returns a `READY` result with `task=None`; `Task.get_result()` raises `AttributeError`. **Unknown, pending, expired and lost look identical.** |
| Non-JSON argument (datetime, Decimal, UUID, set, model) | `TypeError` at enqueue; nothing stored | set/model: `kombu.exceptions.EncodeError`; nothing published. datetime/Decimal/UUID: **the message is published, the caller gets `TypeError` and no ID, and the worker stores a `FAILURE`** |
| JSON coercion of arguments | tuple → list, int keys → str, bytes → str; 2**63+1 preserved | Same |
| Non-JSON return value (set, datetime, bytes, object) | `FAILED` with `TypeError` recorded | set/object: `FAILED` (`EncodeError`). **datetime and bytes: `SUCCESSFUL`, returned as Python datetime/bytes**, not JSON values |
| Queue / alias validation | `InvalidTask` for a queue outside the alias's `QUEUES`; `InvalidTaskBackend` for an unknown alias; both before anything is stored | Same |
| Routing | A worker serves one alias and its queue list (`--backend`, `--queue-name`); a default-alias `ops` row is not run by an `ops`-alias worker | The alias does not route; only the Celery queue name does. Django's `"default"` queue is sent to Celery's `celery` queue. One `-Q ops` worker ran `ops` tasks from both aliases |
| `enqueue()` inside `atomic()`, then commit | The task row commits with the transaction; the worker starts after commit and sees the data | **Task ran during the transaction and did not see the row** |
| `enqueue()` inside `atomic()`, then rollback | The task vanishes with the rollback (`TaskResultDoesNotExist`); it never runs | **Task ran anyway and reported `SUCCESSFUL` on missing data** |
| `transaction.on_commit(partial(t.enqueue, ...))` | Runs after commit; data visible | Same |
| One SIGTERM or SIGINT during a task | Worker finishes the task (about 6 s), exits 0, result `SUCCESSFUL` | Warm shutdown finishes the task, result `SUCCESSFUL` (exit 0; 1 for SIGINT) |
| Second SIGTERM | Task interrupted and recorded `FAILED` with `SystemExit`; worker exits 0 | Still warm; task finished |
| SIGKILL of the worker | Row stays `RUNNING` indefinitely; a restarted worker does not reclaim it and pruning ignores it | Default early ack: **message lost**; result stays `READY` indefinitely. With explicit `task_acks_late`, `task_reject_on_worker_lost` and a 10 s `visibility_timeout`, the message stayed unacknowledged in Redis and was redelivered about 103 s after the restart. The command ran again from the start (at-least-once) |
| Retention | `prune_db_task_results`: 14-day default, per alias, only the `default` queue unless `--queue-name '*'`, finished rows only; a pruned ID raises `TaskResultDoesNotExist` | Redis key TTL ≈86 400 s observed (`result_expires` 1 day); after expiry, see "unknown" above |
| `takes_context` | `attempt == 1` and the correct result ID | Same |

Ownership metadata, observed on both backends: nothing identifies who enqueued a task or who may read it. The DB row stores `id, status, enqueued/started/finished_at, args_kwargs, priority, task_path, worker_ids, queue_name, backend_name, run_after, return_value, exception_class_path, traceback`. Celery extended results store `args, kwargs, name, queue, result, status, traceback, worker, date_done, retries, children, task_id`. Any process holding a result ID can call `get_result()`. An `actor_id` passed as a task kwarg comes back in `result.kwargs` to whoever asks. The result ID works as a bearer token, not authority. DB `get_result()` also looks rows up by ID across aliases (*source*).

5.2 backport, observed: identical behaviour, but the API lives in `django_tasks`, `"django_tasks"` joins `INSTALLED_APPS`, and two exceptions are renamed (`InvalidTaskError`, `InvalidTaskBackendError` instead of `InvalidTask`, `InvalidTaskBackend`). The harness needed exactly one import switch ([compat.py](../../spikes/task_backends/spikeapp/compat.py)).

6.1, observed: no behavioural difference from 6.0. *Source/docs* differences: `Task` becomes picklable, `@task(**kwargs)` is passed to a backend's `task_class`, and `BaseTaskBackend.task_class` is documented.[9] Django 6.1 is inside `Django<7`, but the package classifiers still name only 5.2 and 6.0.

Documented versus observed: the docs' JSON and `on_commit` guidance held on both backends.[1] Celery broke the documented `get_result()` contract (`TaskResultDoesNotExist` for a missing result) and the JSON contract for return values. The docs' datetime example message differs slightly from what Django raises at enqueue (`Unsupported type`), with the same `TypeError` class.

### Capability checks a runner needs

- **Flags that can be checked:** the alias exists (`InvalidTaskBackend`); `supports_get_result` is true, which rejects ImmediateBackend, DummyBackend and Celery without a result backend in one check; the queue is in `backend.queues` (`InvalidTask` at `.using()`). Defer, priority and async support are not needed for a first runner.
- **Not expressed by any flag:** whether a missing result raises, whether enqueue joins the caller's transaction, whether return values are JSON-normalised, whether a killed task is recovered, and whether results expire. These have to be handled defensively by the runner, or ruled out by supporting only a backend whose behaviour has been observed.

### Operational requirements (django-tasks-db)

- Add `django_tasks_db` to `INSTALLED_APPS` (plus `django_tasks` on 5.2) and run migrations. The queue is one table in the application database.
- Run `manage.py db_worker --backend <alias> --queue-name <queues>` under a process supervisor, with `--no-reload`: reload defaults to `DEBUG`. Give it a stop grace period at least as long as the longest allowed command, and don't send a second signal early.
- Nothing recovers crashed work. A row left `RUNNING` needs operator action. Retries are the application's decision, since commands may not be idempotent.
- Schedule `prune_db_task_results --backend <alias> --queue-name '*'` with an explicit retention period.
- SQLite behaved identically with one worker (the backend uses exclusive transactions). Concurrent workers on SQLite were not tested.

### Celery decision

django-tasks-celery 0.1.1 installed and ran reliably against a real broker and worker, but it is **not suitable as the first runner backend**:
- unknown or lost results are indistinguishable from pending ones;
- a killed worker loses the command under default settings (opt-in `acks_late` recovers it only at-least-once, after roughly 100 s);
- rolled-back transactions still dispatch;
- a failed `enqueue()` can still publish a message;
- return values bypass JSON normalisation.

These are adapter and Celery-default semantics, not configuration mistakes in the harness. Revisit when the adapter matures. Projects with Celery can still start their own Celery tasks from ordinary button callbacks without conversion.

## Recommendation / Philosophy fit

Need: launch allow-listed management commands without blocking admin requests. The Django Tasks contract is enough for dispatch; we don't build another queue abstraction.

**First runner boundary:**
1. Depend only on the Tasks contract: `task`, `.using(backend=alias)`, `enqueue`, `get_result` and the three exceptions. Import it through one private switch between `django.tasks` and `django_tasks`, not through a queue interface.
2. Take one explicit backend alias setting, with no silent use of `"default"`. A system check fails when the alias is missing or `supports_get_result` is false, so ImmediateBackend and DummyBackend can never become "background" execution. *Shipped:* `ADMIN_EXTENSIONS["COMMANDS_TASK_BACKEND"]`, check `E101`, plus explicit Immediate/Dummy refusal.
3. Document and test **django-tasks-db** as the supported backend: native on 6.0, and on 5.2 through `django-tasks-db[compat]`. Other backends are "may work, unverified". Celery is excluded for now (above).
4. Always enqueue through `transaction.on_commit`. This is required on Celery-like backends and harmless on the DB backend. *Shipped resolution:* the launch view is `non_atomic_requests` for every Django database alias, and it refuses to launch while any connection is still inside `atomic()`. Without a history model, a run deferred to a later commit could never return its reference.
5. Payload: registered command key plus JSON-safe validated options; nothing else. The task body rechecks the registry, converts its bounded output to JSON itself, and never relies on the backend to reject non-JSON.
6. Protected results, a firm choice for v1: no new model. The launch view returns a **signed reference** (`django.core.signing` with a runner-specific salt) binding result ID, backend alias and initiating user ID. The status view requires a valid signature, a matching `request.user`, and the command's permission, before calling `get_result`. Also pass `actor_id` in task kwargs so the stored record corroborates the reference. This supports "the initiator sees their run". Listing past runs or letting *other* admins view a run needs minimal metadata persistence. That is a product decision to take explicitly, not something to slip in.
7. Show "result no longer available" for `TaskResultDoesNotExist` (pruned or unknown). Show "still running after N minutes; the worker may have stopped" past a configured timeout instead of polling forever. No automatic retry.

Independence: the backend packages remain application-selected optional dependencies. Buttons, JSON and filters install and import nothing from Tasks. Switching aliases keeps our task body and enqueue call, but pending work and retained results stay on the old backend: drain them first.

Safety: allowlist rechecked in the worker, noninteractive commands only, bounded output, signed and permission-checked result access, visible failure when the queue is unavailable.

Scope/proof: the spike covered dispatch, result, failure, JSON, routing, transaction, shutdown and retention on real workers. It did not cover concurrent workers, long-running output streaming, deferred or priority execution, or production supervisors. The runner slice must re-prove allowed and denied runs, worker failure and protected retrieval end to end against django-tasks-db on 5.2 and 6.0.

## Sources

Observed evidence: `spikes/task_backends/` harness (commit named in the spike report); raw per-lane JSON and worker logs are regenerated under `artifacts/task-backend-spike/`.

[1] https://docs.djangoproject.com/en/6.0/topics/tasks (checked 2026-09-24, `stable/6.0.x` docs/topics/tasks.txt)
[2] https://docs.djangoproject.com/en/6.0/ref/tasks
[3] https://docs.djangoproject.com/en/6.0/ref/contrib/admin/actions
[4] https://pypi.org/project/django-tasks-db/0.13.0/ (README; `[compat]` extra requires django-tasks>=0.12.0 on Django<6.0)
[5] https://pypi.org/project/django-tasks-celery/0.1.1/ (README: Django>=6.0,<7; `CELERY_RESULT_EXTENDED=True`)
[6] https://pypi.org/pypi/django-tasks-celery/json
[7] https://pypi.org/project/django-tasks/0.12.0/
[8] https://raw.githubusercontent.com/django/django/stable/6.0.x/docs/ref/contrib/admin/index.txt
[9] https://docs.djangoproject.com/en/6.1/ref/tasks (`task(**kwargs)`, `BaseTaskBackend.task_class`)
