# Installation

Each feature is its own small distribution, selected with an extra of `django-extensions-admin`.
`pip install "django-extensions-admin[buttons,repl]"` installs the buttons and the REPL, and not a
single file of the filters, the environment indicator or anything else. Installing a feature never
turns it on: each one needs its own setting, `INSTALLED_APPS` entry, URL or declaration.

| Extra | Distribution | Adds |
| --- | --- | --- |
| `buttons` | `django-extensions-admin-buttons` | changelist, change-form and row buttons |
| `jsonwidget` | `django-extensions-admin-jsonwidget` | the JSON field editor and read-only rendering |
| `filters` | `django-extensions-admin-filters` | range and choice list filters |
| `commands` | `django-extensions-admin-commands` | the management-command runner (you add a Tasks backend) |
| `branding` | `django-extensions-admin-branding` | a logo and brand colours |
| `environment` | `django-extensions-admin-environment` | the environment indicator |
| `repl` | `django-extensions-admin-repl` | the REPL, with `django-extensions-admin-panel` and `channels` |
| `all` | every distribution above | every feature that ships |

The core depends on Django alone. The REPL brings Channels; no other feature brings a dependency.
Each feature distribution pins the core to the same version, so they always move together.

## From a checkout

Version 0.1.0 is **not yet published on PyPI**. Build the wheels from a checkout and install them
from `dist/`:

```bash
git clone https://github.com/dmmeteo/django-extensions-admin
cd django-extensions-admin
python3 -m venv .venv && . .venv/bin/activate
pip install build
for project in . packages/*; do python -m build --wheel --outdir dist "$project"; done
pip install "Django>=5.2,<7" "channels>=4.1"     # third-party dependencies, from PyPI
pip install --no-index --find-links dist "django-extensions-admin[buttons,repl]"
```

`--no-index` keeps pip from looking the unpublished names up on PyPI, where anyone could register
them: the `django-extensions-admin*` wheels come only from `dist/`. Channels is needed only for
`[repl]`. Editable installs (`pip install -e`) of the split packages are not supported: install the
built wheels, and rebuild after a change.

## `INSTALLED_APPS`

Add the core app **before** `django.contrib.admin`, plus the app of each page-wide feature you
selected (the environment indicator, the panel and the REPL), also before the admin:

```python
INSTALLED_APPS = [
    "django_extensions_admin",
    "django_extensions_admin.environment",   # with [environment]
    "django_extensions_admin.panel",         # with [repl]
    "django_extensions_admin.repl",          # with [repl]
    "django.contrib.admin",
    ...
]
```

If the core app ends up after `django.contrib.admin`, the project-wide JSON default still applies:
it back-fills the admins that were already registered. `manage.py check` warns
(`django_extensions_admin.W001`, `W002`) about a setting whose feature is not installed or not in
`INSTALLED_APPS`, so a shared settings file degrades instead of failing. Each feature's page shows the
rest of its adoption.

## Adding and removing features

Add a feature later with another extra, for example
`pip install --no-index --find-links dist "django-extensions-admin[buttons,repl,environment]"`.
`pip uninstall django-extensions-admin-<feature>` removes one feature's files and leaves the others in
place. The REPL's panel and Channels stay until you remove them too
(`pip uninstall django-extensions-admin-panel channels`).

Before uninstalling, delete the feature's declarations: the mixin and button lists, the widget
override, the `list_filter` entries, the command routes and registrations, your `base_site.html`, the
environment setting, or the REPL's settings, routes and app entries. The package has no model, no
migration and no data format of its own. Button handlers stay ordinary methods, JSONField data stays
as stored, and commands stay ordinary management commands. Queued runs and results live in
django-tasks-db's table, so let them finish and prune them before you uninstall that backend. Each
feature's page lists its exact removal steps.
