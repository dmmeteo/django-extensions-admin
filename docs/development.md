# Development

## Demo

```bash
bash scripts/demo.sh
# http://127.0.0.1:8765/admin/            demo/demo (superuser), operator/operator (staff)
# http://127.0.0.1:8765/admin/commands/   a db_worker runs beside the server
```

Loopback only, a disposable SQLite file and generated data. The script builds the nine wheels and
installs them with `[all]`, so the demo runs what a project would install. Every page shows a "Demo"
environment badge (`DEMO_ENVIRONMENT=` hides it), and the REPL is enabled for the superuser
(`DEMO_REPL=0` turns it off, `DEMO_PANEL_SIDE=left` docks the panel left). The server is a single
ASGI process, as the REPL requires. `DEMO_PORT=9000 bash scripts/demo.sh` changes the port.

The demo shows every button placement, including one handler in two places and one denied by
permission, and the JSON cases worth seeing: nested values, Unicode, numbers JavaScript cannot
represent, HTML-looking strings, a payload over 200 KB in plain mode, and a read-only rendering.
Readings and devices carry dates, instants and numbers for the range filters, with sightings just
after and just before local midnight so the timezone boundary is visible. Devices have a region
dropdown and status and tag checkbox lists, with enough tags to bring up the search box. The command
runner offers one read-only `demo_report` command whose free-text note shows HTML-looking output as
plain text. The demo is branded through `demo/templates/admin/base_site.html` and `BRANDING` in its
settings; delete that template to see the stock admin.

## The gate

```bash
bash scripts/verify.sh
```

Every stage is required, and the gate ends with `GATE PASSED` or exits non-zero. It runs, in order:

1. Lint: Ruff and `node --check` on our own JavaScript.
2. A naming check against earlier working names.
3. A wheel and sdist build of all nine distributions. Each wheel must contain exactly its own source
   root, no file may belong to two distributions, siblings pin each other exactly, the core depends
   on Django alone and the REPL on Channels alone. The vendored terminal must match its published
   hashes, and `twine check --strict` must accept every file.
4. Isolated installs through the public extras, probed with `python -I` from an empty directory:
   bare, each extra on its own, buttons with REPL, all, adding a feature and removing two, and every
   sdist. Each probe proves the installed files are the gate's wheels byte for byte, that no
   unselected feature has a module, file or dependency on disk, that a missing feature's names fail
   with the extra to install, and that the selected features pass system checks. Then the README
   quickstart runs with ordinary pip, and a new `startproject` adopts the REPL, logs in, starts a
   session and restarts the server.
5. The test suite on three lanes against the installed wheels, including real pseudo-terminal REPL
   sessions and WebSocket authorization.
6. The command runner end to end against a separately started `db_worker` process on every lane.
7. Headless-browser journeys with screenshots in `artifacts/browser/`, including the tools panel and
   REPL against a real daphne process on both sides, narrow and wide.
8. A `ty` type report against the installed Django and Channels sources. It is reported, not gating.
9. A check that the README media still match the UI files they were captured from.

`docker/ci.Dockerfile` is a capped runtime for the gate: Chromium, Node, uv and the three Pythons.
[Compatibility](compatibility.md) lists the versions each lane installs.

The worker journeys also run against PostgreSQL: set `WORKER_PG=host:port` (user, password and
database `deadmin`) and run
`DJANGO_SETTINGS_MODULE=worker_tests.settings python tests/runtests.py worker_tests`.

## Continuous integration

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs the part of the gate that is reliable on
a hosted Linux runner: lint, the nine wheels built from the checkout, and the test suite and worker
journeys on the same three lanes against those wheels. The artifact checks, isolated installs and
browser journeys run only in `scripts/verify.sh`.

## Media

`bash scripts/capture_media.sh`, run in the gate's runtime after the gate passed, writes the README
GIF and the REPL page screenshot twice: `features.gif` and `panel-repl.png` in the light theme,
`features-dark.gif` and `panel-repl-dark.png` in the dark theme, all under `docs/media/`. The browser
prefers the light or the dark colour scheme and the stock admin draws its own theme. Every frame is a
screenshot of the running demo admin after a real click, POST, filter, drag or keystroke into a
server-owned PTY, on generated data and demo accounts, and the capture fails if a frame's computed
page colours do not match its theme. `docs/media/manifest.json` records the capture context, the
theme and hash of each file and the hashes of the UI files the frames show. The gate fails when one
of those files changes without a new capture.

## Releasing

[RELEASING.md](../RELEASING.md) is the checklist for an upload. Nothing in this repository uploads.
