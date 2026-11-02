"""Enqueuer-side driver. Each call is a separate process and prints one JSON document.

The orchestrator runs these around a separately started worker, so every result is
read back by a process that neither enqueued nor executed the task.
"""

import datetime
import decimal
import json
import os
import time
import uuid

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from spikeapp import tasks
from spikeapp.compat import (
    TASKS_MODULE,
    InvalidTask,
    InvalidTaskBackend,
    TaskResultDoesNotExist,
    task_backends,
)
from spikeapp.models import Marker


def _error(exc):
    return {"raised": f"{type(exc).__module__}.{type(exc).__qualname__}", "message": str(exc)}


def dump(result):
    """Everything a caller can learn from a TaskResult, without assuming it succeeded."""
    data = {
        "id": result.id,
        "status": str(result.status),
        "is_finished": result.is_finished,
        "backend": result.backend,
        "task": getattr(result.task, "module_path", None),
        "queue": getattr(result.task, "queue_name", None),
        "args": result.args,
        "kwargs": result.kwargs,
        "enqueued_at": result.enqueued_at,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "worker_ids": result.worker_ids,
        "attempts": result.attempts,
        "errors": [
            {"exception": e.exception_class_path, "traceback_tail": e.traceback[-300:]}
            for e in result.errors
        ],
    }
    try:
        data["return_value"] = result.return_value
    except Exception as exc:
        data["return_value"] = _error(exc)
    return data


def get(result_id, backend="default"):
    try:
        return dump(task_backends[backend].get_result(result_id))
    except Exception as exc:
        return _error(exc)


def enqueue(task_name, backend=None, queue=None, **kwargs):
    t = getattr(tasks, task_name)
    if backend or queue:
        t = t.using(backend=backend, queue_name=queue)
    result = t.enqueue(**kwargs)
    return {"id": result.id, "status": str(result.status), "backend": result.backend}


class Command(BaseCommand):
    help = "Drive one step of the task-backend spike and print JSON."

    def add_arguments(self, parser):
        parser.add_argument("action")
        parser.add_argument("target", nargs="?")
        parser.add_argument("--backend", default=None)
        parser.add_argument("--queue", default=None)
        parser.add_argument("--kwargs", default="{}")
        parser.add_argument("--timeout", type=float, default=30)
        parser.add_argument("--hold", type=float, default=3)

    def handle(self, *args, action, target, **options):
        data = getattr(self, f"do_{action}")(target, **options)
        data = {"action": action, "enqueuer": {"pid": os.getpid()}, **data}
        self.stdout.write(json.dumps(data, default=str, indent=1))

    def do_caps(self, target, **options):
        aliases = {}
        for alias in settings.TASKS:
            b = task_backends[alias]
            aliases[alias] = {
                "class": f"{type(b).__module__}.{type(b).__qualname__}",
                "queues": sorted(b.queues),
                "supports_defer": b.supports_defer,
                "supports_async_task": b.supports_async_task,
                "supports_get_result": b.supports_get_result,
                "supports_priority": b.supports_priority,
                "checks": [str(m) for m in b.check()],
            }
        data = {"django": settings.DJANGO_VERSION, "tasks_module": TASKS_MODULE}
        data["aliases"] = aliases
        data["db_vendor"] = settings.DATABASES["default"]["ENGINE"]
        if settings.BACKEND == "celery":
            from spike_project.celery import app

            conf = app.conf
            data["celery"] = {
                k: str(conf.get(k))
                for k in (
                    "result_expires",
                    "task_acks_late",
                    "task_track_started",
                    "task_default_queue",
                    "result_extended",
                    "worker_prefetch_multiplier",
                )
            }
        return data

    def do_enqueue(self, target, backend, queue, kwargs, **options):
        try:
            return enqueue(target, backend, queue, **json.loads(kwargs))
        except Exception as exc:
            return _error(exc)

    def do_get(self, target, backend, **options):
        return {"result": get(target, backend or "default")}

    def do_wait(self, target, backend, timeout, **options):
        """Poll until finished or timeout, recording every status the caller could see."""
        seen, start = [], time.monotonic()
        while True:
            current = get(target, backend or "default")
            status = current.get("status", current.get("raised"))
            if not seen or seen[-1][1] != status:
                seen.append((round(time.monotonic() - start, 2), status))
            if current.get("is_finished") or time.monotonic() - start > timeout:
                break
            time.sleep(0.2)
        return {"trajectory": seen, "timed_out": not current.get("is_finished"), "result": current}

    def do_contrast(self, target, **options):
        """ImmediateBackend runs inside this process; DummyBackend never runs at all."""
        out = {}
        for alias in ("immediate", "dummy"):
            try:
                r = tasks.echo.using(backend=alias).enqueue(payload=alias)
                out[alias] = {"on_enqueue": dump(r), "get_result": get(r.id, alias)}
            except Exception as exc:
                out[alias] = _error(exc)
        return out

    def do_invalid(self, target, **options):
        cases = {
            "unknown_queue": lambda: tasks.echo.using(queue_name="nope"),
            "queue_not_on_alias": lambda: tasks.echo.using(backend="ops"),
            "unknown_alias": lambda: tasks.echo.using(backend="nope").enqueue(),
        }
        out = {}
        for name, case in cases.items():
            try:
                value = case()
                out[name] = {"accepted": repr(value)[:200]}
            except (InvalidTask, InvalidTaskBackend) as exc:
                out[name] = _error(exc)
            except Exception as exc:
                out[name] = {"unexpected": True, **_error(exc)}
        return out

    def do_json(self, target, **options):
        """Where each non-JSON argument fails, and what a JSON-ish one turns into."""
        samples = {
            "tuple": (1, 2),
            "int_keys": {1: "a"},
            "big_int": 2**63 + 1,
            "datetime": datetime.datetime.now(datetime.UTC),
            "decimal": decimal.Decimal("1.10"),
            "uuid": uuid.uuid4(),
            "set": {1, 2},
            "bytes": b"raw",
            "model": Marker(tag="unsaved"),
        }
        out = {}
        for name, value in samples.items():
            tag = f"json-{name}-{uuid.uuid4().hex[:6]}"
            try:
                r = tasks.echo.enqueue(payload=value, tag=tag)
                out[name] = {"accepted": True, "id": r.id, "tag": tag, "args_seen": r.kwargs}
            except Exception as exc:
                out[name] = {"accepted": False, "tag": tag, **_error(exc)}
        return {"samples": out}

    def do_txn(self, target, hold, **options):
        """Enqueue read_row inside a transaction that then commits, rolls back or defers."""
        mode, tag, ids = target, f"txn-{target}-{uuid.uuid4().hex[:6]}", []
        t0 = time.monotonic()
        try:
            with transaction.atomic():
                Marker.objects.create(tag=tag)
                if mode == "on_commit":
                    transaction.on_commit(lambda: ids.append(tasks.read_row.enqueue(tag=tag).id))
                else:
                    ids.append(tasks.read_row.enqueue(tag=tag).id)
                time.sleep(hold)
                if mode == "rollback":
                    raise RuntimeError("deliberate rollback")
        except RuntimeError:
            pass
        ended_at = time.time()
        return {
            "mode": mode,
            "tag": tag,
            "ids": ids,
            "held_seconds": hold,
            "elapsed": round(time.monotonic() - t0, 2),
            "transaction_ended_at": ended_at,
            "row_exists_now": Marker.objects.filter(tag=tag).exists(),
        }

    def do_ownership(self, target, backend, **options):
        """What a holder of nothing but the ID learns, and what the store keeps per result."""
        out = {"result": get(target, backend or "default")}
        if settings.BACKEND == "db":
            from django_tasks_db.models import DBTaskResult

            out["stored_fields"] = [f.name for f in DBTaskResult._meta.get_fields()]
        else:
            import redis

            client = redis.Redis.from_url(settings.CELERY_RESULT_BACKEND)
            key = f"celery-task-meta-{target}"
            raw = client.get(key)
            out["redis_key"] = key
            out["ttl_seconds"] = client.ttl(key)
            out["stored_fields"] = sorted(json.loads(raw)) if raw else None
            out["raw_meta"] = json.loads(raw) if raw else None
        return out

    def _redis(self, db):
        import redis

        return redis.Redis.from_url(f"{os.environ['SPIKE_REDIS']}/{db}")

    def do_scan(self, target, **options):
        """Celery only: every stored result, keyed by the tag its kwargs carried."""
        client, found = self._redis(1), {}
        for key in client.scan_iter("celery-task-meta-*"):
            meta = json.loads(client.get(key))
            tag = (meta.get("kwargs") or {}).get("tag")
            if tag:
                found[tag] = {
                    "id": meta.get("task_id"),
                    "status": meta.get("status"),
                    "result": meta.get("result"),
                    "traceback_tail": (meta.get("traceback") or "")[-300:],
                }
        return {"by_tag": found}

    def do_broker(self, target, **options):
        """Celery only: what the Redis broker still holds (queued and unacknowledged)."""
        client = self._redis(0)
        return {
            "queued": {q: client.llen(q) for q in ("celery", "ops")},
            "unacked": client.hlen("unacked"),
            "unacked_index": client.zcard("unacked_index"),
        }

    def do_count(self, target, **options):
        from django_tasks_db.models import DBTaskResult

        return {
            "by_status": {
                s: DBTaskResult.objects.filter(status=s).count()
                for s in ("READY", "RUNNING", "SUCCESSFUL", "FAILED")
            }
        }

    def do_missing(self, target, backend, **options):
        """Unknown and malformed IDs: does the backend say 'no such result'?"""
        return {
            "random_uuid": get(str(uuid.uuid4()), backend or "default"),
            "garbage": get("not-a-real-id", backend or "default"),
            "via_task_get_result": self._task_get_result(str(uuid.uuid4())),
            "does_not_exist_class": f"{TaskResultDoesNotExist.__module__}.TaskResultDoesNotExist",
        }

    def _task_get_result(self, result_id):
        try:
            return dump(tasks.echo.get_result(result_id))
        except Exception as exc:
            return _error(exc)
