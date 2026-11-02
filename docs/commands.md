# Management commands

Installed with the `commands` extra; see [installation](installation.md).

Launch an explicit allow-list of management commands from the admin. A Django Tasks worker
runs them, so the admin request never waits, and the user who launched a run sees its status
and output. Adoption is explicit: installing the app adds no route, and none of the other
features imports a Tasks package.

```python
# admin.py - autodiscovered in the web process and in the worker alike (see below)
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

## Setup

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

## Registering a command

`register(name, *, permission, form=None, description=None)`

- **`name`** is the management command. Nothing unregistered can be launched, whatever the
  browser sends.
- **`permission`** is required, as `"app_label.codename"` and checked with
  `user.has_perm`. Use an existing model permission or a custom `Meta.permissions` entry.
- **`form`** is an ordinary `forms.Form`. Its field names are the command's option names
  (`dest`), and its `cleaned_data` becomes the `call_command()` keyword arguments. Leave it
  out for a command without options; the page then asks for an explicit Run.
- **`description`** is the label. It defaults to the command name.

**Blank options.** A field that is not required and is left blank is not passed, so the
command's own argparse default applies. "Blank" means the cleaned value is one of the
field's own `empty_values` (`None`, `""`, an empty list), or an empty queryset. Everything
else is passed as cleaned, including `0` and an unticked `BooleanField`'s `False`. Ordinary
multi-value fields work unchanged:
- `MultipleChoiceField` and `ModelMultipleChoiceField`, where the worker looks the objects
  up again;
- split fields such as `SplitDateTimeField`, which are sent as their sub-inputs.

**Where to register.** Register at import time of a module that both the web process and the
worker load. With the default `django.contrib.admin` (`AdminConfig`), every app's `admin.py`
is autodiscovered in each process that calls `django.setup()`, `db_worker` included, so
`admin.py` works. With `SimpleAdminConfig`, `autodiscover()` usually runs from `urls.py`,
which the worker never imports. Register from your `AppConfig.ready()` instead. A worker that
lacks a registration refuses the run: it fails as "not a registered admin command", and
nothing runs.

The system checks catch these mistakes:
- an unknown command;
- a field that is not one of the command's options;
- a missing, unknown or inline backend.

`register()` itself refuses these, as `ImproperlyConfigured`:
- a duplicate;
- a permission not written as `"app_label.codename"`;
- file fields;
- fields named `stdout`, `stderr` or `interactive`.

## Pages and statuses

`/admin/commands/` lists the registered commands the user may run. It is not a list of runs.
Each command has a stock admin form. **Run** posts it, queues the run and redirects to that
run's result page:

| Status | Shown when |
| --- | --- |
| Queued | Waiting for a worker. The page reloads itself every 3 s with a `<meta>` refresh; no JavaScript. |
| Running | A worker has claimed it. |
| Succeeded | Captured `stdout` and `stderr`, escaped. |
| Failed | The exception type and message (or `SystemExit: exit code N` for a command that calls `sys.exit()` with a non-zero code), plus the output written before it. Never the traceback. |
| Unavailable | The result was pruned, is unknown, or belongs to a backend alias that is no longer configured. |

A run still queued or running after `COMMANDS_STALE_AFTER` stops reloading and shows a
warning. A running run's warning says the worker may have stopped. A queued run's warning asks
whether a worker is serving the alias. Runs are never retried automatically.

## What is enforced

- **Launch is POST-only and CSRF-protected.** A GET shows the form and queues nothing.
- **Every view runs through `admin_site.admin_view`.** An active staff login is required, and
  each view checks the command's permission itself. Hiding a link is not a security boundary.
- **The payload is the form's submitted values, as JSON, plus the command key and user id.**
  Before queueing, the values are validated a second time; any that would come back
  different are refused.
- **The worker trusts none of the payload.** It checks, in order:
  - the key, against its own registry;
  - the launching user: still an active **staff** member, the same boundary as the admin
    pages, and still holding the permission;
  - the options, against the registered form.

  Only then does it call `call_command()`. It passes `interactive=False` when the command has
  that option. The user id travels as a string, so UUID and other non-integer primary keys
  work.
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
- **What a failure stores is bounded too.**
  - **The stored record** is a bounded summary: an error line of up to 2,000 characters, plus
    the bounded output. The command's original exception is not chained into it.
  - **The worker's log** gets the full original exception, logged at ERROR by
    `django_extensions_admin.commands`.
  - **Exit codes:** a `sys.exit()` with a non-zero code fails the run, and `sys.exit(0)` counts
    as success.
  - **Worker shutdown:** the `SystemExit` that `db_worker` raises on a second SIGTERM still
    stops the worker.
- **Misconfiguration is refused, never worked around.** An unset or unknown alias, the
  `ImmediateBackend` or `DummyBackend`, or a backend that cannot read results back produces
  a system check error (`django_extensions_admin.E101`). The pages show the same error and
  offer no Run button. A POST returns 503. Nothing ever runs inline. For test or development
  settings that deliberately point the alias at `DummyBackend` or `ImmediateBackend`, add
  `SILENCED_SYSTEM_CHECKS = ["django_extensions_admin.E101"]` there. That lets `test`,
  `runserver` and `migrate` start; the pages still refuse to run anything.
- **Queue failures are shown, not hidden.** If the backend raises during an enqueue, the page
  answers 503 and says the run *may not* have been queued. It never claims either way,
  because a backend can store the run before it fails. django-tasks-db inserts the row, then
  sends `task_enqueued`, and a receiver that raises leaves a stored run that a worker will
  still execute. Check before running a non-idempotent command again. The definite refusals
  (no usable backend, an open transaction) say "Nothing was queued".

## Transactions and `ATOMIC_REQUESTS`

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

## Settings

All under `ADMIN_EXTENSIONS`:

| Key | Default | Meaning |
| --- | --- | --- |
| `COMMANDS_TASK_BACKEND` | `None` | The `settings.TASKS` alias that runs commands. Required; Django's `"default"` is never assumed. |
| `COMMANDS_OUTPUT_LIMIT` | `20000` | Characters kept from each of stdout and stderr. |
| `COMMANDS_STALE_AFTER` | `1800` | Seconds before a queued or running run is reported as possibly stuck. |

## Backends

**django-tasks-db** is the only tested backend:
- Django 6.0: `django.tasks`, native.
- Django 5.2: `django_tasks`, through `[compat]`.

Other backends that can read results back get a system check warning (`W101`), not a promise.
Celery (django-tasks-celery 0.1.1) is not supported: lost and unknown results look like
pending ones, and rolled-back transactions still dispatch. The evidence is in
[the decision note](decisions/actions-and-task-execution.md).

## Limitations

- **Visibility.** A run is shown to its initiator only. There is no run list, history or dashboard,
  and no way to show a run to another admin.
- **What it runs.** Options only: no positional arguments and no file uploads. The form is built with
  `data=` alone, without the request. A blank optional field is left out rather than passed, so it
  cannot pass an explicit `None` or `""`.
- **What the worker rechecks.** The worker has no request and no `AdminSite`. It rechecks active staff
  plus the command permission, not a project's customised `AdminSite.has_permission()`.
- **What it captures.** Only `self.stdout` and `self.stderr`, not `print()` or logging. Output arrives
  when the run finishes; nothing is streamed.
- **What it does not do.** No cancellation, retries, scheduling or priorities. A run whose worker was
  killed stays "running" until it is pruned.
- **Where it launches from.** Launching is refused from inside an open database transaction.

## Removing the command runner

1. Remove the `commands.urls(...)` line, the `commands.register(...)` calls and
   `COMMANDS_TASK_BACKEND`. The commands remain ordinary management commands.
2. Let queued runs finish, then prune or drop the results. They live in django-tasks-db's
   table, not ours.
3. Remove `django_tasks_db` and `django_tasks` from `INSTALLED_APPS` and uninstall them if
   nothing else uses them.

The package itself has no model and no migration.
