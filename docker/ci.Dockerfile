# The runtime for `bash scripts/verify.sh` in a capped container: Chromium and Node from the
# pinned Playwright image, uv, and the three CPython versions the gate's lanes use. The source is
# mounted at run time; the gate itself installs Django and the test dependencies from PyPI.
#
#   docker build -f docker/ci.Dockerfile -t django-extensions-admin-ci docker/
#   docker run --rm --init --user "$(id -u):$(id -g)" --cap-drop=ALL --security-opt no-new-privileges \
#     --memory 1536m --cpus 2 --shm-size 256m -v "$PWD:/work" -w /work \
#     -e HOME=/tmp/home -e TMPDIR=/tmp django-extensions-admin-ci bash scripts/verify.sh
FROM ghcr.io/astral-sh/uv:0.11.15@sha256:e590846f4776907b254ac0f44b5b380347af5d90d668138ca7938d1b0c2f98d3 AS uv

FROM mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27
COPY --from=uv /uv /uvx /usr/local/bin/
# The Playwright image's fontconfig resolves `monospace` to a CJK font, and Chromium then gives a
# <textarea> and a <pre> different fallbacks; DejaVu Sans Mono is the usual Linux default.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && fc-match monospace | grep -q DejaVu
ENV LANG=C.UTF-8
RUN export UV_PYTHON_INSTALL_DIR=/opt/python UV_NO_CACHE=1 \
 && uv python install 3.12.13 3.13.13 3.14.5 \
 && for version in 3.12 3.13 3.14; do ln -sf "$(uv python find --managed-python "$version")" "/usr/local/bin/python$version"; done \
 && chmod -R a+rX /opt/python
# The gate finds these interpreters on PATH and never downloads another. Chromium for
# Playwright 1.63.0 is already in /ms-playwright; the gate installs the matching Python package.
ENV UV_PYTHON_DOWNLOADS=never \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python3.12 --version && python3.13 --version && python3.14 --version && node --version && uv --version
