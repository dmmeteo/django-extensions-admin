"""Run every spike scenario for one lane against real, separately started workers.

    python orchestrate.py --lane db60 --python .venvs/spike-db60/bin/python --out DIR

The store/broker must already be running (run.sh starts disposable containers).
Workers are child processes in their own sessions; all of them are stopped in
`finally`. Output: DIR/lane.json (every observation) and DIR/commands.log.
"""

import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import uuid

HERE = pathlib.Path(__file__).resolve().parent


class Lane:
    def __init__(self, args):
        self.name = args.lane
        self.python = pathlib.Path(args.python).absolute()
        self.out = pathlib.Path(args.out).absolute()
        self.out.mkdir(parents=True, exist_ok=True)
        self.celery = os.environ.get("SPIKE_BACKEND") == "celery"
        self.markers = self.out / "markers"
        self.env = {
            **os.environ,
            "SPIKE_MARKERS": str(self.markers),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
        }
        self.log = (self.out / "commands.log").open("a")
        self.workers = {}
        self.started = 0
        self.steps = {}

    # ---- processes -------------------------------------------------------
    def run(self, argv, env=None):
        t0 = time.monotonic()
        proc = subprocess.run(
            argv, cwd=HERE, env=env or self.env, capture_output=True, text=True, check=False
        )
        took = round(time.monotonic() - t0, 2)
        self.log.write(f"$ {' '.join(map(str, argv))}\n# exit={proc.returncode} {took}s\n")
        if proc.returncode or proc.stderr.strip():
            self.log.write(proc.stderr[-2000:] + "\n")
        self.log.flush()
        return proc

    def spike(self, *argv):
        proc = self.run([self.python, "manage.py", "spike", *argv])
        try:
            return {"exit": proc.returncode, **json.loads(proc.stdout)}
        except json.JSONDecodeError:
            return {"exit": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr[-2000:]}

    def worker_argv(self, name, queue, backend):
        if self.celery:
            celery = self.python.parent / "celery"
            return [
                celery, "-A", "spike_project.celery", "worker", "-Q", queue,
                "-n", f"{name}@%h", "--concurrency", "1", "-l", "INFO",
                "--without-heartbeat", "--without-gossip", "--without-mingle",
            ]  # fmt: skip
        return [
            self.python, "manage.py", "db_worker", "--no-reload", "--no-startup-delay",
            "--interval", "0.2", "--worker-id", name, "--queue-name", queue,
            "--backend", backend, "-v", "2",
        ]  # fmt: skip

    def start_worker(self, name, queue="default", backend="default", extra_env=None):
        if self.celery and queue == "default":
            queue = "celery"  # the adapter drops queue_name "default"; Celery routes to "celery"
        argv = self.worker_argv(name, queue, backend)
        self.started += 1
        logfile = (self.out / f"worker-{self.started:02d}-{name}.log").open("w")
        env = {**self.env, **(extra_env or {})}
        proc = subprocess.Popen(
            argv,
            cwd=HERE,
            env=env,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.workers[name] = proc
        self.log.write(f"$ {' '.join(map(str, argv))} &  # pid={proc.pid}\n")
        time.sleep(4 if self.celery else 1.5)
        return {"name": name, "pid": proc.pid, "argv": [str(a) for a in argv], "ps": self.ps(proc)}

    def ps(self, proc):
        tree = subprocess.run(
            ["ps", "-o", "pid,ppid,pgid,etime,args", "--no-headers", "-g", str(proc.pid)],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        return [line.strip()[:200] for line in tree.splitlines()]

    def stop_worker(self, name, sig=signal.SIGTERM, repeat=0, timeout=30):
        proc = self.workers.pop(name)
        t0 = time.monotonic()
        if sig == signal.SIGKILL:
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.send_signal(sig)
            for _ in range(repeat):
                time.sleep(0.5)
                proc.send_signal(sig)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            rc = f"timeout, killed: {proc.wait()}"
        leftover = self.ps(proc)
        return {
            "name": name,
            "signal": signal.Signals(sig).name,
            "sent": 1 + repeat,
            "exit": rc,
            "exit_after_s": round(time.monotonic() - t0, 2),
            "leftover_processes": leftover,
        }

    def stop_all(self):
        for name in list(self.workers):
            self.stop_worker(name, timeout=15)

    # ---- helpers ---------------------------------------------------------
    def enqueue(self, task, backend=None, queue=None, **kwargs):
        argv = ["enqueue", task, "--kwargs", json.dumps(kwargs)]
        if backend:
            argv += ["--backend", backend]
        if queue:
            argv += ["--queue", queue]
        return self.spike(*argv)

    def wait(self, result_id, backend=None, timeout=30):
        argv = ["wait", result_id, "--timeout", str(timeout)]
        if backend:
            argv += ["--backend", backend]
        return self.spike(*argv)

    def marker(self, tag, stage="start", timeout=0.0):
        path = self.markers / f"{tag}.{stage}"
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        return float(path.read_text()) if path.exists() else None

    def tag(self, prefix):
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    def step(self, name, fn):
        print(f"--- {self.name}: {name}", flush=True)
        try:
            self.steps[name] = fn()
        except Exception as exc:
            self.steps[name] = {"step_error": f"{type(exc).__name__}: {exc}"}
        self.dump()

    def dump(self):
        (self.out / "lane.json").write_text(json.dumps(self.steps, indent=1, default=str))

    # ---- scenarios -------------------------------------------------------
    def s_durability(self):
        tag = self.tag("durable")
        queued = self.enqueue("echo", payload="durable", tag=tag)
        before = self.spike("get", queued["id"])
        time.sleep(2)
        still = self.spike("get", queued["id"])
        worker = self.start_worker("w1")
        done = self.wait(queued["id"])
        where = (done.get("result", {}).get("return_value") or {}).get("where", {})
        return {
            "enqueued_with_no_worker": queued,
            "status_right_after": before["result"].get("status"),
            "status_after_2s_no_worker": still["result"].get("status"),
            "worker_started": worker,
            "result_from_fresh_process": done,
            "separation": {
                "enqueuer_pid": queued["enqueuer"]["pid"],
                "reader_pid": done["enqueuer"]["pid"],
                "worker_pid": worker["pid"],
                "task_pid": where.get("pid"),
                "task_ppid": where.get("ppid"),
                "task_ran_in_worker_tree": worker["pid"] in (where.get("pid"), where.get("ppid")),
            },
        }

    def s_trajectory(self):
        r = self.enqueue("echo", payload="trajectory", sleep=2)
        return {"enqueued": r, "waited": self.wait(r["id"])}

    def s_failure(self):
        r = self.enqueue("fail", message="deliberate failure")
        return {"enqueued": r, "waited": self.wait(r["id"])}

    def s_context(self):
        r = self.enqueue("with_context")
        return {"enqueued": r, "waited": self.wait(r["id"])}

    def s_command(self):
        ok = self.enqueue("run_command", key="hello", options={"name": "spike"})
        denied = self.enqueue("run_command", key="flush", options={})
        return {"allowed": self.wait(ok["id"]), "denied": self.wait(denied["id"])}

    def s_json(self):
        probe = self.spike("json")
        time.sleep(3)
        stored = self.spike("scan").get("by_tag", {}) if self.celery else {}
        samples = {}
        for name, sample in probe.get("samples", {}).items():
            entry = dict(sample)
            if sample.get("accepted"):
                entry["waited"] = self.wait(sample["id"], timeout=15)
            entry["task_started_anyway"] = self.marker(sample["tag"]) is not None
            if self.celery:
                entry["in_result_store"] = stored.get(sample["tag"])
            samples[name] = entry
        returns = {}
        for kind in ("set", "datetime", "bytes", "object"):
            r = self.enqueue("bad_return", kind=kind)
            returns[kind] = self.wait(r["id"], timeout=15) if "id" in r else r
        return {"arguments": samples, "return_values": returns}

    def s_invalid(self):
        return self.spike("invalid")

    def s_missing(self):
        return self.spike("missing")

    def s_queues(self):
        default_alias_ops = self.enqueue("echo_ops", payload="default alias, ops queue")
        ops_alias_ops = self.enqueue("echo_ops", backend="ops", payload="ops alias, ops queue")
        time.sleep(3)
        out = {
            "enqueued": {"default_alias_ops_queue": default_alias_ops, "ops_alias": ops_alias_ops},
            "after_3s_default_worker_only": {
                "default_alias_ops_queue": self.spike("get", default_alias_ops["id"])["result"],
                "ops_alias": self.spike("get", ops_alias_ops["id"], "--backend", "ops")["result"],
            },
        }
        out["ops_worker"] = self.start_worker("w-ops", queue="ops", backend="ops")
        time.sleep(3)
        out["after_ops_alias_worker"] = {
            "default_alias_ops_queue": self.spike("get", default_alias_ops["id"])["result"],
            "ops_alias": self.spike("get", ops_alias_ops["id"], "--backend", "ops")["result"],
        }
        if not self.celery:
            out["default_ops_worker"] = self.start_worker("w-default-ops", queue="ops")
            out["after_default_alias_ops_worker"] = self.wait(default_alias_ops["id"], timeout=10)
            out["stopped_default_ops"] = self.stop_worker("w-default-ops")
        out["stopped_ops"] = self.stop_worker("w-ops")
        return out

    def s_transactions(self):
        out = {}
        for mode in ("commit", "rollback", "on_commit"):
            txn = self.spike("txn", mode, "--hold", "3")
            started = self.marker(txn["tag"], timeout=10)
            entry = {"txn": txn, "task_marker_started_at": started}
            if started is not None:
                entry["task_started_before_transaction_ended"] = (
                    started < txn["transaction_ended_at"]
                )
            entry["results"] = [self.wait(i, timeout=10) for i in txn["ids"]]
            out[mode] = entry
        return out

    def s_ownership(self):
        r = self.enqueue("echo", payload="owned", actor_id=42)
        waited = self.wait(r["id"])
        return {"enqueued": r, "waited": waited, "inspected": self.spike("ownership", r["id"])}

    def shutdown_case(self, name, sig, repeat=0, extra_env=None):
        worker = self.start_worker(name, extra_env=extra_env)
        tag = self.tag(name)
        r = self.enqueue("slow", seconds=6, tag=tag)
        started = self.marker(tag, timeout=15)
        stopped = self.stop_worker(name, sig=sig, repeat=repeat)
        broker = self.spike("broker") if self.celery else None
        return {
            "broker_after_stop": broker,
            "worker": worker,
            "enqueued": r,
            "task_started": started is not None,
            "stopped": stopped,
            "task_finished_marker": self.marker(tag, "end") is not None,
            "status_after_stop": self.spike("get", r["id"])["result"],
            "tag": tag,
        }

    def s_shutdown(self):
        self.stop_worker("w1")  # the scenarios below need exclusive control of the queue
        out = {
            "sigterm_once": self.shutdown_case("w-term", signal.SIGTERM),
            "sigterm_twice": self.shutdown_case("w-term2", signal.SIGTERM, repeat=1),
            "sigint_once": self.shutdown_case("w-int", signal.SIGINT),
        }
        killed = self.shutdown_case("w-kill", signal.SIGKILL)
        time.sleep(2)
        killed["restart_worker"] = self.start_worker("w-after-kill")
        killed["after_restart_15s"] = self.wait(killed["enqueued"]["id"], timeout=15)
        killed["broker_after_restart"] = self.spike("broker") if self.celery else None
        killed["restarted_worker_saw_marker_again"] = self.marker(killed["tag"], "end") is not None
        out["sigkill"] = killed
        self.stop_worker("w-after-kill")
        if self.celery:
            acks = {"SPIKE_CELERY_ACKS_LATE": "1"}
            late = self.shutdown_case("w-kill-late", signal.SIGKILL, extra_env=acks)
            late["restart_worker"] = self.start_worker("w-after-kill-late", extra_env=acks)
            late["after_restart_130s"] = self.wait(late["enqueued"]["id"], timeout=130)
            late["broker_after_restart"] = self.spike("broker")
            out["sigkill_acks_late_visibility_10s"] = late
            self.stop_worker("w-after-kill-late")
        self.start_worker("w1")
        return out

    def s_retention(self):
        if self.celery:
            r = self.enqueue("echo", payload="ttl")
            self.wait(r["id"])
            return {"ownership_probe": self.spike("ownership", r["id"])}
        r = self.enqueue("echo", payload="to prune")
        self.wait(r["id"])
        manage = [self.python, "manage.py"]
        prune = [*manage, "prune_db_task_results", "--queue-name", "*"]
        out = {"before": self.spike("count")}
        default_run = self.run([*prune])
        out["default_14_days"] = {"exit": default_run.returncode, "out": default_run.stdout}
        dry = self.run([*prune, "--min-age-days", "0", "--dry-run"])
        out["dry_run_0_days"] = {"exit": dry.returncode, "out": dry.stdout}
        real = self.run([*prune, "--min-age-days", "0"])
        out["prune_0_days_default_alias"] = {"exit": real.returncode, "out": real.stdout}
        ops = self.run([*prune, "--min-age-days", "0", "--backend", "ops"])
        out["prune_0_days_ops_alias"] = {"exit": ops.returncode, "out": ops.stdout}
        out["after"] = self.spike("count")
        out["get_pruned_id"] = self.spike("get", r["id"])["result"]
        return out

    def s_help(self):
        if self.celery:
            proc = self.run([self.python.parent / "celery", "--version"])
            return {"celery_version": proc.stdout.strip()}
        return {
            "db_worker": self.run([self.python, "manage.py", "db_worker", "--help"]).stdout,
            "prune": self.run([self.python, "manage.py", "prune_db_task_results", "--help"]).stdout,
        }

    def main(self):
        try:
            self.step("help", self.s_help)
            self.step("capabilities", lambda: self.spike("caps"))
            self.step("contrast_immediate_dummy", lambda: self.spike("contrast"))
            self.step("missing_ids", self.s_missing)
            self.step("invalid_selection", self.s_invalid)
            self.step("durability_and_separation", self.s_durability)
            self.step("status_trajectory", self.s_trajectory)
            self.step("failure", self.s_failure)
            self.step("context", self.s_context)
            self.step("command_shape", self.s_command)
            self.step("json_constraints", self.s_json)
            self.step("queues_and_aliases", self.s_queues)
            self.step("transactions", self.s_transactions)
            self.step("ownership", self.s_ownership)
            self.step("shutdown", self.s_shutdown)
            self.step("retention", self.s_retention)
        finally:
            self.stop_all()
            self.dump()
            self.log.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--out", required=True)
    Lane(parser.parse_args()).main()
    sys.exit(0)
