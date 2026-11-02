# Django Tasks backend spike

Evidence harness behind [the task-execution decision note](../../docs/decisions/actions-and-task-execution.md).
It is **not product code**: nothing here is imported by `src/`, installed with the wheel or
required by the package. Delete the directory when the note no longer needs re-checking.

Each run starts disposable containers (`--rm`, `127.0.0.1` random ports, `deadmin-spike-*`
names), migrates a throwaway database, then drives harmless tasks through **separately started
worker processes**:

```bash
bash spikes/task_backends/run.sh db60            # Django 6.0 + django-tasks-db, PostgreSQL
bash spikes/task_backends/run.sh db52            # Django 5.2 + django-tasks-db[compat]
bash spikes/task_backends/run.sh db61            # Django 6.1 + django-tasks-db
bash spikes/task_backends/run.sh db60 sqlite     # same, SQLite file instead of a container
bash spikes/task_backends/run.sh celery60        # Django 6.0 + django-tasks-celery, Redis
```

Requires `uv` and Docker (for SQLite runs, Docker only for the Celery lane). Environments go
in `.venvs/spike-<lane>`; observations go in `artifacts/task-backend-spike/<lane>-<db>/`
(`lane.json`, `commands.log`, one log per worker, `environment.txt`). Both are gitignored.

What the orchestrator exercises: capabilities per alias, Immediate/Dummy as contrast only,
unknown result IDs, invalid queue/alias selection, enqueue with no worker running, process
separation, the status trajectory, failure, `takes_context`, a registry-shaped `call_command`
task, JSON argument and return constraints, queue/alias routing, transaction timing,
result ownership metadata, worker shutdown (SIGTERM, a second SIGTERM, SIGINT, SIGKILL) and
result pruning or expiry.

Teardown check after a run:

```bash
docker ps -a --filter name=deadmin-spike      # nothing listed
pgrep -af 'db_worker|spike_project.celery'    # nothing listed
```
