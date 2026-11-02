"""An opt-in Django shell in the admin's tools panel, on a PTY the server owns.

It runs arbitrary Python with the application's privileges, so it is off until
``ADMIN_EXTENSIONS["REPL_ENABLED"]`` is True, and then only for active staff superusers,
checked on every HTTP request and WebSocket connection. One ASGI server process hosts the
sessions; see docs/repl.md.
"""
