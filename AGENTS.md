# django-extensions-admin

A reusable Django library: small, independent, opt-in utilities for the stock Django admin.
It ships buttons, a JSON field widget, range and choice list filters, a management-command
runner on Django Tasks, restrained branding, an environment indicator, and an opt-in REPL in a
shared tools panel. The core distribution is `django-extensions-admin` and the module is
`django_extensions_admin`; each feature is its own distribution under `packages/<feature>`,
selected by an extra. This checkout directory keeps an earlier working
name, which `scripts/verify.sh` rejects in code and shipped files.

## Authority

- [PHILOSOPHY.md](PHILOSOPHY.md) holds the accepted product principles. Read it before
  planning, changing the roadmap, designing an API, implementing or reviewing a change. Put
  its short **Philosophy fit** check in plans and implementation packets. Keep principles in
  that one file.
- A principle, an accepted scope boundary or a safety boundary changes only through explicit
  owner direction. Surface a conflict for a product decision instead of reinterpreting the
  principle or rewriting prose to match code.
- The code and tests are the behavioural specification of what ships.
  [README.md](README.md) and the `docs/` reference pages describe it for users. Neither they
  nor [ROADMAP.md](ROADMAP.md) override PHILOSOPHY.md.
- A ROADMAP candidate or unchecked item is not permission to implement it. A roadmap item
  starts only after the owner selects it. Take one bounded outcome at a time.

## Where things are

Read the document that matches the task, not all of them.

- What ships, what is open, what is deferred or out of scope: [ROADMAP.md](ROADMAP.md).
- Changing a feature's behaviour or API: its reference page
  ([buttons](docs/buttons.md), [JSON widget](docs/json-widget.md),
  [list filters](docs/filters.md), [management commands](docs/commands.md),
  [branding](docs/branding.md), [environment](docs/environment.md), [panel](docs/panel.md),
  [REPL](docs/repl.md)) and its section in [ARCHITECTURE.md](ARCHITECTURE.md), which holds
  module boundaries, packaging, native contracts, dependency and removal rules, and their
  reasons. A feature's source is `packages/<feature>/src/django_extensions_admin/`.
- Why an earlier choice was made, especially for the command runner, task backends or result
  access: [the decision index](docs/adr/index.md). Each entry says what its record decided.
  The current record explains why django-tasks-db was chosen, why Celery is deferred and why
  results use a signed reference instead of a run model. Its evidence harness is
  [spikes/task_backends](spikes/task_backends/README.md), which is not product code.
- Installation, the security summary, tested versions, the demo and the gate:
  [installation](docs/installation.md), [security](docs/security.md),
  [compatibility](docs/compatibility.md) and [development](docs/development.md).
- Preparing or checking a release: [RELEASING.md](RELEASING.md).

## Current state

Implemented and covered by `bash scripts/verify.sh`: buttons, the JSON widget, range filters,
choice filters, the command runner on django-tasks-db, branding, the environment indicator, the
tools panel and the REPL, each installable on its own, on the Python and Django lanes listed in
[docs/compatibility.md](docs/compatibility.md). Version 0.1.0 is built and checked but not published on PyPI. The
selective-installation outcome awaits independent review and the owner's High-risk sign-off. The
open outcomes are the owner's PyPI upload and the first consumer pilot. ROADMAP has the details,
the deferred decisions and the future naming request.

## Working rules

- The core wheel's only runtime dependency is Django. Each feature distribution depends on the
  core with an exact pin, not on another feature; the REPL alone also needs the panel and
  Channels. Task backends, IPython and ASGI servers are optional packages the application
  selects. No two distributions ship the same file.
- The tests import the installed wheels, not `src/`: `scripts/verify.sh` builds and installs them.
- New library persistence (a model or migration) needs a product decision first. Showing a
  command run to anyone but its initiator, or listing runs, is such a decision.
- Claim only what the gate tests. Name a third-party admin integration as compatible only
  after a test for it exists.
- `README.md` is also the PyPI page, and each `packages/*/README.md` is its distribution's. They
  use absolute GitHub links only, and the gate fails on relative ones. The core sdist ships only
  the package, README, ROADMAP and LICENSE; each feature sdist only its source, README and LICENSE. RELEASING step 3
  depends on the "not yet published on PyPI" notes and the review-branch links in the READMEs.
- The consumer pilot runs in a real consumer application. Nothing in this repository stands
  in for it, and application business logic stays out of the library.
- Use behaviour-driven red, green, refactor and keep `bash scripts/verify.sh` as the gate. Add
  tests for plausible failure modes, not quotas or every helper. Use a few browser journeys for
  selection, layout, fallback and form ownership, without replaying the full rule matrix at
  every layer.

## Keeping this context current

- After verified work, update only the documents it affects: README or a `docs/` page for
  usage and limitations, ROADMAP for status, ARCHITECTURE for boundaries, a decision record
  plus its entry in `docs/adr/index.md` for a weighed choice, and this file for paths and
  working rules. An implementation-only change needs no documentation edit.
- After context loss (compaction, a new session, a handoff), re-read this file and the
  constraints relevant to the task before consequential work.
