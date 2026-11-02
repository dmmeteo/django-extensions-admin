# Compatibility

Exactly what `bash scripts/verify.sh` runs, and nothing is claimed beyond it.

| | Tested |
| --- | --- |
| Python and Django lanes | Django 5.2 LTS on CPython 3.14 and on 3.12; Django 6.0 on CPython 3.13 |
| Isolated installs | bare, each extra on its own, buttons with REPL, all, adding a feature, removing two, and every sdist, on CPython 3.14 |
| Command-runner backend | django-tasks-db 0.13.0 (with django-tasks 0.12 on 5.2), SQLite; PostgreSQL 16 checked separately |
| REPL | channels 4.3.2 on every lane; IPython 9.17.1 on the 3.12 and 3.13 lanes; django-extensions 4.1 (`shell_plus`) on the 3.13 lane; daphne 4.2.3 in the browser journeys |
| Browser | Chromium via Playwright 1.63 (headless), Django 6.0 on CPython 3.13 |
| OS | Linux x86-64 |

The declared bounds are `requires-python = ">=3.12"` and `Django>=5.2,<7`. Other combinations inside
those bounds (Django 6.0 on 3.12 or 3.14, Django 5.2 on 3.13) are plausible but **untested** by the
gate. Windows, macOS, Firefox and Safari are untested. The REPL needs Linux: it is system check error
`django_extensions_admin.E504` elsewhere.

## Admin customisations

- The panel and the environment indicator add a layer of `admin/base_site.html`. A project whose own
  `admin/base_site.html` extends `admin/base.html` directly bypasses them.
- Admin skins that ship their own `admin/base.html` or `base_site.html` are not supported by
  branding, and neither is a third-party stylesheet that redefines the same colour variables.
- No third-party admin integration is claimed: none has a test.
