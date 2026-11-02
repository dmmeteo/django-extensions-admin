"""Capture docs/media from real journeys on the demo project, then write docs/media/manifest.json.

    bash scripts/capture_media.sh        # builds the wheels and an environment, then runs this

Every frame is a screenshot of the running admin after a real action: a button POST, a filter
GET, the JSON editor's Format button, a REPL session typing into a server-owned PTY, a drag of
the panel's edge. The journey runs twice, in a browser that prefers the light and then the dark
colour scheme, so the stock admin draws its own light and dark themes; each frame fails unless
the page's computed colours match the theme. The data is the demo's generated data; the accounts
are the demo's own. The manifest records the hashes of the UI files the frames show, so the gate
can tell when the media no longer match the code.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
MEDIA = ROOT / "docs" / "media"
FRAMES = Path(os.environ.get("CAPTURE_FRAMES", ROOT / "artifacts" / "capture"))
VIEWPORT = {"width": 1440, "height": 860}
GIF_WIDTH = 960
# The README GIF and the REPL page screenshot for each colour scheme; the light ones keep their
# original names.
THEMES = {
    "light": ("features.gif", "panel-repl.png"),
    "dark": ("features-dark.gif", "panel-repl-dark.png"),
}
UI_SOURCES = [
    "packages/panel/src/django_extensions_admin/panel/static/django_extensions_admin/panel/panel.js",
    "packages/panel/src/django_extensions_admin/panel/static/django_extensions_admin/panel/panel.css",
    "packages/panel/src/django_extensions_admin/panel/static/django_extensions_admin/panel/boot.js",
    "packages/panel/src/django_extensions_admin/panel/templates/django_extensions_admin/panel/panel.html",
    "packages/panel/src/django_extensions_admin/panel/templates/django_extensions_admin/panel/toggle.html",
    "packages/repl/src/django_extensions_admin/repl/static/django_extensions_admin/repl/repl.js",
    "packages/repl/src/django_extensions_admin/repl/static/django_extensions_admin/repl/repl.css",
    "packages/repl/src/django_extensions_admin/repl/templates/django_extensions_admin/repl/tool.html",
    "packages/environment/src/django_extensions_admin/environment/static/django_extensions_admin/environment/environment.css",
    "packages/environment/src/django_extensions_admin/environment/templates/django_extensions_admin/environment/indicator.html",
    "packages/buttons/src/django_extensions_admin/static/django_extensions_admin/buttons.css",
    "packages/filters/src/django_extensions_admin/static/django_extensions_admin/filters.css",
    "packages/jsonwidget/src/django_extensions_admin/static/django_extensions_admin/json-widget.css",
    "packages/jsonwidget/src/django_extensions_admin/static/django_extensions_admin/json-widget.js",
]
SCREEN = """() => {
  const term = document.getElementById("admin-ext-repl").adminExtRepl.terminal;
  const buffer = term.buffer.active;
  const rows = [];
  for (let y = 0; y < buffer.length; y += 1) {
    rows.push(buffer.getLine(y)?.translateToString(true) ?? "");
  }
  return rows.join("\\n");
}"""
THEME = """() => {
  const root = getComputedStyle(document.documentElement);
  return {
    prefers_dark: matchMedia("(prefers-color-scheme: dark)").matches,
    data_theme: document.documentElement.dataset.theme ?? null,
    body_bg: root.getPropertyValue("--body-bg").trim(),
    body_fg: root.getPropertyValue("--body-fg").trim(),
    background: getComputedStyle(document.body).backgroundColor,
    color: getComputedStyle(document.body).color,
  };
}"""
GRID = """() => {
  const repl = document.getElementById("admin-ext-repl").adminExtRepl;
  const p = repl.proposed(), t = repl.terminal, s = repl.ptySize;
  return p && t && s && t.cols === p.cols && t.rows === p.rows
    && s.cols === t.cols && s.rows === t.rows;
}"""


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def channels(css):
    return [float(part) for part in css[css.index("(") + 1 : css.index(")")].split(",")[:3]]


class Recorder:
    def __init__(self, page, theme):
        self.page = page
        self.theme = theme
        self.frames = []
        self.evidence = []

    def frame(self, caption, hold=1.6):
        computed = self.page.evaluate(THEME)
        # The light admin has a near-white page background, the dark admin a near-black one.
        rgb = channels(computed["background"])
        dark = self.theme == "dark"
        if computed["prefers_dark"] != dark or not (max(rgb) < 64 if dark else min(rgb) > 192):
            raise RuntimeError(f"{self.theme} frame drew another theme: {computed}")
        screen = self.page.evaluate(
            "() => document.getElementById('admin-ext-repl')?.adminExtRepl?.terminal"
            f" ? ({SCREEN})() : null"
        )
        path = FRAMES / self.theme / f"{len(self.frames):02d}.png"
        self.page.screenshot(path=str(path))
        self.frames.append((path, caption, hold))
        self.evidence.append(
            {
                "frame": len(self.frames),
                "caption": caption,
                "page": "/" + self.page.url.split("/", 3)[3],
                "computed": computed,
                "terminal": [line for line in (screen or "").splitlines() if line.strip()][-6:],
                "sha256": sha256(path),
            }
        )
        print(f"{self.theme} frame {len(self.frames):02d} {caption} {computed}", flush=True)
        return path


def caption(image, text):
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=22)
    box = draw.textbbox((0, 0), text, font=font)
    width, height = box[2] - box[0], box[3] - box[1]
    x, y = 16, image.height - height - 28
    draw.rounded_rectangle(
        (x - 10, y - 8, x + width + 10, y + height + 14), radius=6, fill=(17, 17, 17)
    )
    draw.text((x, y), text, font=font, fill=(255, 255, 255))
    return image


def write_gif(frames, target):
    images, durations = [], []
    for path, text, hold in frames:
        image = Image.open(path).convert("RGB")
        image = image.resize(
            (GIF_WIDTH, round(image.height * GIF_WIDTH / image.width)), Image.LANCZOS
        )
        images.append(caption(image, text).quantize(colors=96, method=Image.Quantize.MEDIANCUT))
        durations.append(int(hold * 1000))
    images[0].save(
        target, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True
    )


def server(env):
    from browser_tests.asgi_server import AsgiServer

    return AsgiServer(FRAMES / "daphne.log", env).start()


def login(page, url):
    page.goto(f"{url}/admin/login/?next=/admin/")
    page.fill("#id_username", "demo")
    page.fill("#id_password", "demo")
    page.click('input[type="submit"]')
    page.wait_for_selector("#user-tools")


def type_line(page, code, expected=None):
    page.locator("#admin-ext-repl [data-role=screen] canvas").click()
    page.keyboard.type(code, delay=15)
    page.keyboard.press("Enter")
    if expected:
        page.wait_for_function(f"(n) => ({SCREEN})().includes(n)", arg=expected, timeout=30000)


def drag(page, dx):
    box = page.locator("#admin-ext-panel [data-panel-role=resize]").bounding_box()
    x, y = round(box["x"] + box["width"] / 2), round(box["y"] + box["height"] / 3)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y, steps=12)
    page.mouse.up()


def journey(page, url, record, png):
    login(page, url)
    page.goto(f"{url}/admin/demoapp/device/")
    record.frame("Buttons: a changelist button, beside Django's own tools")
    page.get_by_role("button", name="Ping all devices").click()
    page.wait_for_selector(".messagelist .success")
    record.frame("Buttons: a CSRF-protected POST, checked server-side")

    page.goto(f"{url}/admin/demoapp/reading/")
    page.fill("input[name='value__range__gte']", "10")
    page.fill("input[name='value__range__lte']", "40")
    page.press("input[name='value__range__lte']", "Enter")
    page.wait_for_url("**value__range__gte=10**")
    record.frame("Filters: a numeric range in the stock sidebar")

    page.get_by_role("link", name="Readings").first.click()
    page.locator("#result_list tbody tr th a").first.click()
    page.wait_for_selector("textarea.admin-ext-json")
    record.frame("JSON widget: indented, highlighted, validated")

    page.goto(f"{url}/admin/")
    record.frame("Environment indicator: the name on every page, header unchanged")
    page.get_by_role("button", name="Tools panel").click()
    page.wait_for_selector("#admin-ext-panel:not([hidden])")
    page.wait_for_selector("#admin-ext-repl [data-action=start]")
    record.frame("Tools panel: docks below the full-width header")
    page.click("#admin-ext-repl [data-action=start]")
    page.wait_for_function(
        "() => document.querySelector('#admin-ext-repl [data-role=state]')?.textContent === 'Live'"
    )
    page.wait_for_function(f"() => ({SCREEN})().includes('In [')", timeout=60000)
    type_line(page, "from demoapp.models import Device", "In [2]")
    type_line(page, "Device.objects.count()", "Out[2]")
    record.frame("REPL: a real Django shell in a server-owned PTY", hold=2.2)
    type_line(
        page,
        'from django.core.management import call_command; call_command("check")',
        "System check identified",
    )
    record.frame("Management commands from the shell: call_command, no new runner", hold=2.2)
    drag(page, -160)
    page.wait_for_function(GRID)
    type_line(page, "import os; os.get_terminal_size()", "os.terminal_size")
    # A resize rebuilds the terminal and replays its output a moment later: wait for the history.
    page.wait_for_function(f"() => ({SCREEN})().includes('System check identified')")
    record.frame("Drag to resize: the PTY follows the terminal grid", hold=2.2)
    # Django's own nav sidebar, collapsed the way its toggle does, to leave the list room.
    page.evaluate("localStorage.setItem('django.admin.navSidebarIsOpen', 'false')")
    page.get_by_role("link", name="Devices").first.click()
    page.wait_for_url("**/demoapp/device/")
    page.wait_for_function(
        "() => document.querySelector('#admin-ext-repl [data-role=state]')?.textContent === 'Live'"
    )
    page.wait_for_function(GRID)
    type_line(page, "Device.objects.count()", "Out[5]")
    record.frame("Same process after navigating: variables and history kept", hold=2.4)
    shot = MEDIA / png
    page.screenshot(path=str(shot))
    return shot


def main():
    from playwright.sync_api import sync_playwright

    MEDIA.mkdir(parents=True, exist_ok=True)
    # The same SQLite file the daphne helper serves (it sets WORKER_USE_TEST_DB).
    env = {
        "DJANGO_SETTINGS_MODULE": "browser_tests.settings",
        "PYTHONPATH": str(ROOT),
        "WORKER_USE_TEST_DB": "1",
    }
    assets, evidence, captions = [], {}, {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for theme, (gif_name, png) in THEMES.items():
            (FRAMES / theme).mkdir(parents=True, exist_ok=True)
            # Fresh data and a fresh server for each theme: the second journey sees what the
            # first saw, not its pinged devices or its live REPL session.
            for command in (["migrate", "--noinput"], ["seed_demo"]):
                subprocess.run(  # noqa: S603 - our own interpreter and arguments
                    [sys.executable, "-m", "django", *command],
                    cwd=ROOT,
                    env={**os.environ, **env},
                    check=True,
                )
            live = server({"BROWSER_REPL": "1", "BROWSER_ENVIRONMENT": "Staging"})
            try:
                context = browser.new_context(viewport=VIEWPORT, color_scheme=theme)
                page = context.new_page()
                page.set_default_timeout(30000)
                record = Recorder(page, theme)
                shot = journey(page, live.url, record, png)
                context.close()
            finally:
                live.stop()
            gif = MEDIA / gif_name
            write_gif(record.frames, gif)
            computed = record.evidence[0]["computed"]
            for path in (shot, gif):
                assets.append(
                    {
                        "path": str(path.relative_to(ROOT)),
                        "theme": theme,
                        "body_background": computed["background"],
                        "sha256": sha256(path),
                        "bytes": path.stat().st_size,
                    }
                )
            evidence[theme] = record.evidence
            captions[theme] = [text for _, text, _ in record.frames]
        chromium = browser.version
        browser.close()
    if captions["light"] != captions["dark"]:
        raise RuntimeError("the light and dark journeys recorded different frames")
    (FRAMES / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    manifest = {
        "captured": datetime.now(UTC).isoformat(timespec="seconds"),
        "context": "demo project, generated data, demo accounts, Chromium headless "
        f"{chromium}, viewport {VIEWPORT['width']}x{VIEWPORT['height']}, light and dark"
        " colour schemes, by scripts/capture_media.py",
        "captions": captions["light"],
        "assets": assets,
        "ui_sources": {source: sha256(ROOT / source) for source in UI_SOURCES},
    }
    (MEDIA / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("captured", "assets")}, indent=2))


if __name__ == "__main__":
    started = time.monotonic()
    main()
    print(f"captured in {time.monotonic() - started:.0f} s")
