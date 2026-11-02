// The REPL tool inside the shared tools panel. The panel owns opening, side and width; this
// file owns the terminal, its session and the WebSocket, and follows the screen's size.
const LAST_KEY = "admin-ext-repl:last-session";
const INPUT_CHUNK = 32 * 1024;
const CLOSE_REVOKED = 4401;
const CLOSE_FORBIDDEN = 4403;
const CLOSE_DISABLED = 4404;

const THEME = {
  background: "#0d1117",
  foreground: "#e6edf3",
  cursor: "#79aec8",
  cursorAccent: "#0d1117",
  selectionBackground: "#264f78",
  black: "#484f58",
  red: "#ff7b72",
  green: "#3fb950",
  yellow: "#d29922",
  blue: "#58a6ff",
  magenta: "#bc8cff",
  cyan: "#39c5cf",
  white: "#b1bac4",
  brightBlack: "#6e7681",
  brightRed: "#ffa198",
  brightGreen: "#56d364",
  brightYellow: "#e3b341",
  brightBlue: "#79c0ff",
  brightMagenta: "#d2a8ff",
  brightCyan: "#56d4dd",
  brightWhite: "#ffffff",
};

const STATE_LABELS = {
  running: ["Live", "live"],
  exited: ["Exited", "warning"],
  ended: ["Ended", "none"],
  expired: ["Expired", "warning"],
};

const tool = document.getElementById("admin-ext-repl");
if (tool) setup(tool);

function setup(tool) {
  const root = document.documentElement;
  const panel = document.getElementById("admin-ext-panel");
  const part = (role) => tool.querySelector(`[data-role="${role}"]`);
  const action = (name) => tool.querySelector(`[data-action="${name}"]`);
  const ui = {
    state: part("state"),
    notice: part("notice"),
    launch: part("launch"),
    backend: part("backend"),
    screen: part("screen"),
    meta: part("meta"),
    start: action("start"),
    end: action("end"),
  };
  const urls = tool.dataset;
  const csrfToken = tool.querySelector("input[name=csrfmiddlewaretoken]").value;
  const encoder = new TextEncoder();
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

  let terminal = null;
  let terminalReady = null;
  // Counts requests for a new terminal; only the latest one may take the screen.
  let replacements = 0;
  let socket = null;
  let session = null;
  let cursor = 0;
  let liveFrom = 0;
  let replaying = false;
  let reconnectDelay = 500;
  let reconnectTimer = null;
  let fitFrame = 0;
  let redrawTimer = null;
  // Attaches sent on this socket and not yet answered. The server answers them in order; frames are
  // dropped until the last one is answered, so a reply to an older attach never opens the way for
  // an older stream onto a newer screen.
  let attaching = 0;
  // The server restarted the stream for another screen: frames wait for a new terminal's attach.
  let stale = false;
  let idleLimit = null;
  // The grid the server last confirmed for the PTY; input sent after it reaches that size.
  let ptySize = null;

  tool.adminExtRepl = {
    get terminal() {
      return terminal?.term ?? null;
    },
    get session() {
      return session;
    },
    get cursor() {
      return cursor;
    },
    get ptySize() {
      return ptySize;
    },
    proposed() {
      return terminal?.fit.proposeDimensions() ?? null;
    },
  };

  function setState(label, kind) {
    ui.state.textContent = label;
    ui.state.dataset.state = kind;
  }

  function setNotice(text) {
    ui.notice.textContent = text || "";
  }

  function adopt(snapshot) {
    session = snapshot;
    browserStore.set(LAST_KEY, snapshot ? snapshot.id : "");
  }

  function formatDuration(seconds) {
    if (seconds % 3600 === 0) return `${seconds / 3600} h`;
    if (seconds % 60 === 0) return `${seconds / 60} min`;
    return `${seconds} s`;
  }

  function renderLive() {
    const [label, kind] = STATE_LABELS.running;
    setState(label, kind);
    ui.launch.hidden = true;
    ui.end.hidden = false;
    ui.meta.textContent = `${session.backend_label} · pid ${session.pid} · ends after ${formatDuration(session.idle_timeout)} without input`;
  }

  function renderStopped(snapshot) {
    const [label, kind] = snapshot ? STATE_LABELS[snapshot.state] : ["Not started", "none"];
    setState(label, kind);
    ui.launch.hidden = false;
    ui.end.hidden = true;
    ui.start.textContent = snapshot ? "Start new session" : "Start session";
    ui.meta.textContent = snapshot
      ? `${snapshot.backend_label} · session ${snapshot.id.slice(0, 8)}`
      : idleLimit && `Sessions end after ${formatDuration(idleLimit)} without input.`;
    if (snapshot?.reason) setNotice(snapshot.reason);
  }

  function renderBackends(data) {
    idleLimit = data.idle_timeout;
    const chosen = ui.backend.value || data.default_backend;
    ui.backend.replaceChildren(
      ...data.backends.map(({ key, label }) => new Option(label, key, false, key === chosen)),
    );
  }

  async function api(method, url, body) {
    const headers = { Accept: "application/json" };
    if (method === "POST") {
      headers["Content-Type"] = "application/json";
      headers["X-CSRFToken"] = csrfToken;
    }
    const response = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      body: method === "POST" ? JSON.stringify(body || {}) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw Object.assign(new Error(data.error || `Request failed with HTTP ${response.status}.`), {
        status: response.status,
      });
    }
    return data;
  }

  async function ensureTerminal() {
    terminalReady ??= newTerminal();
    await terminalReady;
  }

  // ghostty-web 0.4.0 corrupts its WebAssembly memory when a terminal that was resized is later
  // reset or cleared: a following write traps out of bounds (a renderer crash in headless
  // Chromium, a frozen terminal elsewhere). So a terminal is never reset. When the screen has to
  // start over, a new terminal on a new WebAssembly instance replaces it, at the same size.
  // Loading it takes time, in which output, an End, a new session or another redraw can arrive.
  // The old screen stays until then; only the latest request, if still wanted, replaces it, and
  // the cursor starts over with it. Resolves to whether it replaced the screen.
  async function newTerminal(wanted = () => true) {
    const request = ++replacements;
    const { Ghostty, Terminal, FitAddon } = await import(urls.ghosttyUrl);
    const ghostty = await Ghostty.load(urls.wasmUrl);
    if (request !== replacements || !wanted()) return false;
    const old = terminal?.term;
    const focused = Boolean(old) && ui.screen.contains(document.activeElement);
    old?.dispose();
    ui.screen.replaceChildren();
    const monospace = getComputedStyle(root).getPropertyValue("--font-family-monospace").trim();
    const term = new Terminal({
      ghostty,
      cols: old?.cols,
      rows: old?.rows,
      cursorBlink: true,
      fontSize: 13,
      fontFamily: monospace || "monospace",
      scrollback: 5000,
      theme: THEME,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(ui.screen);
    term.onData(sendInput);
    term.onResize(({ cols, rows }) => {
      sendControl({ type: "resize", cols, rows });
      if (cursor > 0) scheduleRedraw();
    });
    terminal = { term, fit };
    cursor = 0;
    stale = false;
    fitTerminal();
    if (focused) term.focus();
    return true;
  }

  function scheduleFit() {
    cancelAnimationFrame(fitFrame);
    fitFrame = requestAnimationFrame(fitTerminal);
  }

  // Not FitAddon.fit(): in ghostty-web 0.4.0 it does nothing for 50 ms after each resize and
  // skips a size equal to the one it proposed last, so the final width of a drag or a quick
  // second key press was dropped and the grid stayed stale until the next redraw refit it.
  function fitTerminal() {
    if (!terminal || ui.screen.clientWidth === 0) return;
    const size = terminal.fit.proposeDimensions();
    if (size && (size.cols !== terminal.term.cols || size.rows !== terminal.term.rows)) {
      terminal.term.resize(size.cols, size.rows);
    }
  }

  // ghostty-web 0.4.0 can also leave stale cells when it reflows rows to a new grid. Once the grid
  // settles, the screen is rebuilt from the server's output log at the new size, the same replay a
  // reload does. Frames are dropped from the new terminal's attach until the server confirms it.
  function scheduleRedraw() {
    clearTimeout(redrawTimer);
    redrawTimer = setTimeout(redraw, 250);
  }

  async function redraw() {
    // A socket still connecting attaches from the new screen's cursor when it opens.
    const live = () => session?.state === "running" && Boolean(socket);
    if (live() && (await newTerminal(live))) attach(session.id);
  }

  function attach(id) {
    if (socket?.readyState !== WebSocket.OPEN) return;
    attaching += 1;
    socket.send(JSON.stringify({ type: "attach", session: id, cursor }));
  }

  function sendControl(message) {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
  }

  function sendInput(data) {
    if (replaying || session?.state !== "running" || socket?.readyState !== WebSocket.OPEN) return;
    const bytes = encoder.encode(data);
    for (let index = 0; index < bytes.length; index += INPUT_CHUNK) {
      socket.send(bytes.subarray(index, index + INPUT_CHUNK));
    }
  }

  function disconnect() {
    clearTimeout(reconnectTimer);
    if (socket) {
      socket.onclose = null;
      socket.close(1000);
      socket = null;
    }
  }

  function connect() {
    disconnect();
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${scheme}//${location.host}${urls.streamPath}`);
    ws.binaryType = "arraybuffer";
    socket = ws;
    setState("Connecting", "warning");
    ws.onopen = () => {
      reconnectDelay = 500;
      attaching = 0;
      stale = false;
      attach(session?.id ?? null);
    };
    ws.onmessage = (event) => {
      if (typeof event.data === "string") onControl(JSON.parse(event.data));
      else onOutput(event.data);
    };
    ws.onclose = (event) => onSocketClosed(ws, event);
  }

  function onControl(message) {
    if (message.type === "attached") {
      attaching -= 1;
      // A newer attach is on its way: this answer, and the stream it starts, are for an older screen.
      if (attaching > 0) return;
      if (message.session && message.reset && cursor > 0) {
        // The server replays from the start: the old screen goes with its terminal.
        stale = true;
        newTerminal().then((replaced) => replaced && attach(message.session.id));
        return;
      }
      if (!message.session) {
        disconnect();
        adopt(null);
        renderStopped(null);
        return;
      }
      ptySize = null;
      adopt(message.session);
      liveFrom = message.live_from;
      if (message.session.state === "running") renderLive();
      scheduleFit();
      sendControl({ type: "resize", cols: terminal.term.cols, rows: terminal.term.rows });
    } else if (message.type === "resized") {
      ptySize = { cols: message.cols, rows: message.rows };
    } else if (message.type === "gap" && !attaching && !stale) {
      setNotice(
        `Earlier output was not retained: replay starts at byte ${message.to}, ${message.to - message.from} bytes are not shown.`,
      );
      cursor = message.to;
    } else if (message.type === "state") {
      adopt(message.session);
      if (message.session.state !== "running") {
        disconnect();
        renderStopped(message.session);
      }
    }
  }

  function onOutput(buffer) {
    if (attaching || stale) return;
    const offset = Number(new DataView(buffer).getBigUint64(0));
    let bytes = new Uint8Array(buffer, 8);
    if (offset > cursor) {
      setNotice(`${offset - cursor} bytes of output were lost in transit and are not shown.`);
    } else if (offset < cursor) {
      bytes = bytes.subarray(cursor - offset);
    }
    const start = Math.max(offset, cursor);
    cursor = start + bytes.length;
    if (!bytes.length) return;
    // Replayed history can contain terminal queries; their synchronous replies must not reach the live REPL.
    replaying = start < liveFrom;
    try {
      terminal.term.write(bytes);
    } finally {
      replaying = false;
    }
  }

  function onSocketClosed(ws, event) {
    if (socket !== ws) return;
    socket = null;
    if (event.code === CLOSE_REVOKED || event.code === CLOSE_FORBIDDEN || event.code === CLOSE_DISABLED) {
      setState("Not authorized", "error");
      setNotice(
        event.code === CLOSE_DISABLED
          ? "The REPL is not enabled on this server."
          : "This browser session is no longer authorized for the REPL. Log in again as an active staff superuser.",
      );
      return;
    }
    if (session?.state === "running") {
      setState("Disconnected", "warning");
      setNotice(`Connection lost. Reconnecting in ${Math.round(reconnectDelay / 100) / 10} s.`);
      reconnectTimer = setTimeout(refresh, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 10000);
    }
  }

  async function refresh() {
    let data;
    try {
      data = await api("GET", urls.stateUrl);
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        setState("Not authorized", "error");
        setNotice(error.message);
        return;
      }
      setState("Disconnected", "error");
      setNotice(`${error.message} Retrying in ${Math.round(reconnectDelay / 1000)} s.`);
      reconnectTimer = setTimeout(refresh, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 10000);
      return;
    }
    renderBackends(data);
    const previous = browserStore.get(LAST_KEY);
    const current = data.session;
    if (previous && current?.id !== previous) {
      setNotice(
        `Session ${previous.slice(0, 8)} no longer exists on the server. It was replaced, or the server restarted and its Python state is gone.`,
      );
    } else if (!current || current.state === "running") {
      setNotice("");
    }
    if (current?.state === "running") {
      await ensureTerminal();
      if (current.id !== session?.id && cursor > 0) await newTerminal();
      adopt(current);
      connect();
    } else {
      adopt(current);
      renderStopped(current);
    }
  }

  async function start() {
    ui.start.disabled = true;
    try {
      const data = await api("POST", urls.startUrl, { backend: ui.backend.value });
      await ensureTerminal();
      if (cursor > 0) await newTerminal();
      adopt(data.session);
      setNotice("");
      connect();
      terminal.term.focus();
    } catch (error) {
      setState("Error", "error");
      setNotice(error.message);
    } finally {
      ui.start.disabled = false;
    }
  }

  async function end() {
    if (!confirm("End this REPL session? The Python process and everything defined in it will be terminated.")) {
      return;
    }
    try {
      const data = await api("POST", urls.endUrl);
      disconnect();
      adopt(data.session);
      renderStopped(data.session);
    } catch (error) {
      setNotice(error.message);
    }
  }

  function focusInside() {
    if (session?.state === "running" && terminal) terminal.term.focus();
    else if (!ui.launch.hidden) ui.backend.focus();
  }

  async function show({ focus }) {
    if (!socket) await refresh();
    scheduleFit();
    if (focus) focusInside();
  }

  function visible() {
    return panel && !panel.hidden && !tool.closest("[role=tabpanel]")?.hidden;
  }

  panel?.addEventListener("admin-ext-panel:show", (event) => {
    if (event.detail.tool === "repl") show({ focus: event.detail.focus });
  });
  new ResizeObserver(scheduleFit).observe(ui.screen);
  ui.start.addEventListener("click", start);
  ui.end.addEventListener("click", end);
  // The panel opened before this module ran (it restores an open panel on load).
  if (visible()) show({ focus: false });
}
