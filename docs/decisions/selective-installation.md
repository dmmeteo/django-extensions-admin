# Selective installation, the tools panel and the REPL

Status: accepted by the owner on 2026-10-30, implemented on branch `feat/unified-tools`, awaiting
independent review and High-risk sign-off before `main`.

## Context

The owner's contract: a project selects, say, buttons and the REPL, does not install the filters, the
environment indicator or any other feature's files, configures only what it selected, and adds more
features later. It also folded the separate REPL project into this repository as an optional feature,
and asked for an environment indicator. ARCHITECTURE.md previously excluded a REPL companion; this
owner direction supersedes that exclusion, not the principles behind it (independent features,
dependencies follow features, install is not activation, stock admin identity, no data models).

## Options weighed

| Option | Result |
| --- | --- |
| One wheel, extras for third-party dependencies only | Every feature's files on every install. Rejected: "hidden" is not "not installed". |
| One source tree, per-distribution builds selecting files (hatchling `force-include` from outside the project) | Prototyped on 2026-10-30: the sdist cannot build its own wheel, so pip installs from sdist fail. Rejected. |
| One distribution per feature with its own source root, one public name with extras | Chosen. Normal packaging; pip adds and removes one feature's files; each sdist is self-contained. |
| Every feature becomes its own Django app | Not needed for features already adopted through the core app; it would add an `INSTALLED_APPS` entry per feature for existing users. Used only for the page-wide features (environment, panel, REPL). |

## Decision

- The core `django-extensions-admin` holds `__init__`, `apps`, `conf` and `admin`, depends on Django
  alone, and exposes extras that pin each feature distribution exactly. Feature distributions live in
  `packages/<feature>/` and install into the shared `django_extensions_admin` directory; the core
  owns its `__init__.py` and no file has two owners.
- Public names resolve lazily and name the missing extra. Template and static paths are unchanged.
- Tests import the installed wheels. Editable installs of the split packages are not supported.
- The REPL is a panel tool, off by default, for active staff superusers, in one ASGI process.
- The panel keeps Django's header full width (owner correction, 2026-10-30) and docks below it.

## Consequences

- Nine distributions release together with one version; RELEASING uploads features before the core.
- The gate proves isolation from built wheels: bare, buttons, REPL, buttons+REPL, environment, all,
  later add and remove, and every sdist.
- Removing a feature is configuration removal plus `pip uninstall django-extensions-admin-<feature>`.
- Recovery: the branch reverts in Git. Nothing is published; PyPI names are unclaimed.
