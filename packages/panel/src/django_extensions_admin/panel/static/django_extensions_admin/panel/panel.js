// The shared tools panel: open and close, the side, the width (drag and keys), and which tool
// shows. A tool listens for "admin-ext-panel:show" and "admin-ext-panel:hide" on the panel and
// follows its own element's size; the panel knows nothing about any tool.
const OPEN_KEY = "admin-ext-panel:open";
const WIDE_KEY = "admin-ext-panel:wide";
const WIDTH_KEY = "admin-ext-panel:width";
const TOOL_KEY = "admin-ext-panel:tool";

// Window-splitter keys. The separator moves with the arrow: ArrowLeft widens a right-hand panel
// and narrows a left-hand one. `outward` is +1 when moving the separator left widens the panel.
const RESIZE_KEYS = {
  ArrowLeft: (width, step, bounds, outward) => width + outward * step,
  ArrowRight: (width, step, bounds, outward) => width - outward * step,
  Home: (width, step, bounds) => bounds.min,
  End: (width, step, bounds) => bounds.max,
};

const panel = document.getElementById("admin-ext-panel");
if (panel) setup(panel);

function setup(panel) {
  const root = document.documentElement;
  const header = document.getElementById("header");
  const toggle = document.querySelector("[data-admin-ext-panel-toggle]");
  const resize = panel.querySelector('[data-panel-role="resize"]');
  const wideButton = panel.querySelector('[data-panel-action="wide"]');
  const closeButton = panel.querySelector('[data-panel-action="close"]');
  const tabs = [...panel.querySelectorAll('[role="tab"]')];
  const outward = panel.dataset.side === "left" ? -1 : 1;
  const storage = (area) => ({
    get(key) {
      try {
        return window[area].getItem(key);
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        window[area].setItem(key, value);
      } catch {}
    },
  });
  const tabStore = storage("sessionStorage");
  const browserStore = storage("localStorage");

  // The panel starts where Django's header ends, wherever its own wrapping, branding or an
  // indicator above it put that edge, and reaches the viewport top once the header scrolls away.
  function placeBelowHeader() {
    const top = header ? Math.max(0, Math.ceil(header.getBoundingClientRect().bottom)) : 0;
    root.style.setProperty("--admin-ext-panel-top", `${top}px`);
  }

  function selectedTool() {
    return tabs.find((tab) => tab.getAttribute("aria-selected") === "true")?.dataset.tool;
  }

  function announce(type, detail = {}) {
    panel.dispatchEvent(new CustomEvent(`admin-ext-panel:${type}`, { detail: { tool: selectedTool(), ...detail } }));
  }

  function selectTool(key, { focus = false } = {}) {
    const chosen = tabs.find((tab) => tab.dataset.tool === key) ? key : tabs[0]?.dataset.tool;
    for (const tab of tabs) {
      const selected = tab.dataset.tool === chosen;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      document.getElementById(tab.getAttribute("aria-controls")).hidden = !selected;
      if (selected && focus) tab.focus();
    }
    tabStore.set(TOOL_KEY, chosen);
    if (!panel.hidden) announce("show", { focus: false });
  }

  function open({ focus = true } = {}) {
    placeBelowHeader();
    panel.hidden = false;
    root.classList.add("admin-ext-panel-docked");
    toggle?.setAttribute("aria-expanded", "true");
    tabStore.set(OPEN_KEY, "1");
    syncWidth();
    if (focus) panel.querySelector('[role="tab"][aria-selected="true"]')?.focus();
    announce("show", { focus });
  }

  function close() {
    panel.hidden = true;
    root.classList.remove("admin-ext-panel-docked");
    toggle?.setAttribute("aria-expanded", "false");
    tabStore.set(OPEN_KEY, "0");
    announce("hide");
    toggle?.focus();
  }

  function setWide(wide) {
    root.classList.toggle("admin-ext-panel-wide", wide);
    wideButton.setAttribute("aria-pressed", String(wide));
    wideButton.textContent = wide ? "Docked width" : "Full width";
    tabStore.set(WIDE_KEY, wide ? "1" : "0");
    syncWidth();
  }

  function panelWidth() {
    return panel.getBoundingClientRect().width;
  }

  // The same bounds as the CSS clamp() on --admin-ext-panel-width.
  function widthBounds() {
    const style = getComputedStyle(root);
    const min = parseFloat(style.getPropertyValue("--admin-ext-panel-min-width"));
    return { min, max: Math.max(min, innerWidth - parseFloat(style.getPropertyValue("--admin-ext-panel-min-page"))) };
  }

  function syncWidth() {
    const { min, max } = widthBounds();
    const width = Math.round(panelWidth());
    resize.setAttribute("aria-valuemin", min);
    resize.setAttribute("aria-valuemax", max);
    resize.setAttribute("aria-valuenow", width);
    resize.setAttribute("aria-valuetext", `${width} pixels wide`);
  }

  function setWidth(width) {
    const { min, max } = widthBounds();
    const clamped = Math.round(Math.min(Math.max(width, min), max));
    root.style.setProperty("--admin-ext-panel-preferred", `${clamped}px`);
    browserStore.set(WIDTH_KEY, String(clamped));
    syncWidth();
  }

  function startResize(event) {
    if (event.button !== 0) return;
    const startX = event.clientX;
    const startWidth = panelWidth();
    const follow = (moved) => setWidth(startWidth + outward * (startX - moved.clientX));
    resize.setPointerCapture(event.pointerId);
    root.classList.add("admin-ext-panel-resizing");
    resize.addEventListener("pointermove", follow);
    resize.addEventListener(
      "lostpointercapture",
      () => {
        resize.removeEventListener("pointermove", follow);
        root.classList.remove("admin-ext-panel-resizing");
      },
      { once: true },
    );
  }

  toggle?.addEventListener("click", () => (panel.hidden ? open() : close()));
  closeButton.addEventListener("click", close);
  wideButton.addEventListener("click", () => setWide(!root.classList.contains("admin-ext-panel-wide")));
  resize.addEventListener("pointerdown", startResize);
  // Keeps focus where it was and stops the drag from starting a text selection.
  resize.addEventListener("mousedown", (event) => event.preventDefault());
  resize.addEventListener("keydown", (event) => {
    const next = RESIZE_KEYS[event.key];
    if (!next || event.altKey || event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    setWidth(next(panelWidth(), event.shiftKey ? 80 : 16, widthBounds(), outward));
  });
  for (const tab of tabs) {
    tab.addEventListener("click", () => selectTool(tab.dataset.tool));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const index = (tabs.indexOf(tab) + step + tabs.length) % tabs.length;
      selectTool(tabs[index].dataset.tool, { focus: true });
    });
  }
  addEventListener("scroll", placeBelowHeader, { passive: true });
  addEventListener("resize", () => {
    placeBelowHeader();
    if (!panel.hidden) syncWidth();
  });
  if (header) new ResizeObserver(placeBelowHeader).observe(header);
  document.addEventListener(
    "keydown",
    (event) => {
      if (event.ctrlKey && !event.altKey && !event.metaKey && event.key === "`") {
        event.preventDefault();
        event.stopPropagation();
        if (panel.hidden) open();
        else close();
      } else if (
        event.key === "Escape" &&
        !panel.hidden &&
        panel.contains(document.activeElement) &&
        !panel.querySelector(".admin-ext-panel-tool:not([hidden])")?.contains(document.activeElement)
      ) {
        close();
      }
    },
    true,
  );

  selectTool(tabStore.get(TOOL_KEY));
  setWide(tabStore.get(WIDE_KEY) === "1");
  if (tabStore.get(OPEN_KEY) === "1") open({ focus: false });
}
