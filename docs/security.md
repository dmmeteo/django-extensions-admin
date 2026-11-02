# Security

Every feature follows the same rules. This page summarises them; each feature's page has the full
list under **What is enforced** or **Security**.

## Nothing is on until you adopt it

Installing a distribution adds files, not behaviour. A feature acts only after its own declaration:
a button list on a `ModelAdmin`, a widget override or `JSON_WIDGET_DEFAULT`, a `list_filter` entry, a
registered command plus its URLs and a Tasks backend, your own `base_site.html` for branding, an
`ENVIRONMENT` name, or `REPL_ENABLED = True` plus the REPL's apps and routes. Installing the app does
not expose a shell, run a command or change a JSON field.

## The server decides

Hiding a control is never the boundary. Every action is checked where it runs:

| Feature | Checked on the server |
| --- | --- |
| [Buttons](buttons.md#what-is-enforced) | POST only, CSRF, `has_module_permission` and the button's permission at the endpoint; objects come through `get_object()`, so a row outside `get_queryset()` is a 404. |
| [Management commands](commands.md#what-is-enforced) | Only registered commands; active staff plus the command's permission on every view; the worker rechecks the registration, the user and the options before `call_command()`; a result is readable only by its initiator through a signed reference. |
| [List filters](filters.md) | A filter narrows the queryset the `ModelAdmin` already authorized; a value it cannot read matches nothing instead of being ignored. |
| [REPL](repl.md#security) | Enabled, authenticated, active, staff and superuser on every HTTP request and WebSocket connection; each user reaches only their own session; start and end are CSRF-protected POSTs that send only a backend name from the server's list; a live stream rechecks the Django session every 10 seconds. |

## The REPL is code execution

The REPL runs arbitrary Python with your web server's privileges, including its settings, secrets and
network access. Enable it only where every active staff superuser may do that, serve the admin over
HTTPS, keep `ALLOWED_HOSTS` explicit (`"*"` with the REPL enabled is system check error
`django_extensions_admin.E503`), and contain the server process with a dedicated OS user, a container
or a VM and egress limits. [The REPL page](repl.md#security) lists what it does and does not protect.

## Output and data

- Button messages, command output, environment names and JSON keys and values are escaped. HTML is
  shown as text, never run.
- Command output is bounded per stream, and a failed run stores a bounded error line, not the
  traceback.
- django-tasks-db registers its own "Task Results" admin, which shows every run's arguments and output
  to superusers and to staff with its view permission. Grant that permission deliberately, or
  unregister that admin.
- The package has no model, no migration and no data format of its own. The panel's width and open
  state live in each browser's local storage.

## Content Security Policy

Branding and the environment indicator use a `<style>` element that takes Django 6.0's `csp_nonce`
when the CSP middleware provides one. The REPL's terminal compiles WebAssembly, so a policy on admin
pages needs `'wasm-unsafe-eval'` in `script-src` for the REPL. The other features need nothing extra.
