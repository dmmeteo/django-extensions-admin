# Releasing

A short checklist so an upload ships what the gate proved, and nothing the README does not
claim. It is not a process beyond that. Nothing in this repository uploads.

## Before any upload

1. The release commit is on `main`, the tree is clean, and `bash scripts/verify.sh` ends with
   `GATE PASSED` on that exact commit. The gate builds the nine wheels and nine sdists into
   `dist/` (the core and eight feature distributions under `packages/`), checks their contents
   and metadata, runs `twine check --strict` and installs every extra on its own, the
   combinations and every sdist into clean environments.
2. The version is `__version__` in `src/django_extensions_admin/__init__.py`, which the core's
   `pyproject.toml` reads, and the `version` and exact `==` sibling pins in each
   `packages/*/pyproject.toml` and in the core's extras. The gate fails unless they all agree.
3. PyPI shows each README from the upload. So the release commit switches README's two "not yet
   published on PyPI" notes (the release-status note and the **Quickstart**) and the one in each
   `packages/*/README.md` to `pip install "django-extensions-admin[...]"`, then reruns the gate.
   If the upload does not happen, revert that commit.
4. Check that each name is still unclaimed: `https://pypi.org/pypi/<name>/json` answers 404 for
   `django-extensions-admin` and each `django-extensions-admin-<feature>`. A name someone else
   registered in the meantime stops the release.
5. Upload exactly the eighteen files in `dist/` from that gate run, feature distributions
   first and the core last, so the core's extras never point at a missing release. Do not
   rebuild in between: record `sha256sum dist/*` from the gate run and compare before the upload.

## Owner-only steps

These need the owner's PyPI and GitHub accounts, and nothing in this repository does them:

- A PyPI account with 2FA. The first successful upload claims each name.
- Optionally, a dry run on TestPyPI first.
- The upload, with an API token or a trusted publisher the owner configures
  (`uv publish` or `twine upload dist/*`).
- Tag `v0.1.0` on the release commit and create the GitHub release.
- Afterwards, `pip install "django-extensions-admin[all]==0.1.0"` into a fresh environment and
  check that `import django_extensions_admin` works and `manage.py check` passes.
