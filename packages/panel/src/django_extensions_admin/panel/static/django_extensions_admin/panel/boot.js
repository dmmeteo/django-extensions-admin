// Runs in <head>, before the first paint, so a docked panel does not make the page jump.
try {
  const root = document.documentElement;
  if (document.currentScript?.dataset.side === "left") root.classList.add("admin-ext-panel-left");
  if (sessionStorage.getItem("admin-ext-panel:open") === "1") root.classList.add("admin-ext-panel-docked");
  if (sessionStorage.getItem("admin-ext-panel:wide") === "1") root.classList.add("admin-ext-panel-wide");
  const width = Number(localStorage.getItem("admin-ext-panel:width"));
  if (Number.isFinite(width) && width > 0) root.style.setProperty("--admin-ext-panel-preferred", `${width}px`);
} catch {}
