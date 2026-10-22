// Fresh Discord Rich Presence Plugin
// Connects Fresh editor to Discord via the local IPC micro-daemon

const editor = getEditor();

// Declare configuration options for the Fresh Settings UI
// Note: Fresh renders settings alphabetically by key name.
// Keys are chosen so 'enabled' sorts first.
editor.defineConfigBoolean("enabled", {
  default: true,
  description: "Enable or disable Discord Rich Presence.",
});

editor.defineConfigString("presencePrefix", {
  default: "Editing",
  description: "Prefix verb displayed before the active filename (e.g. 'Editing', 'Working on').",
});

editor.defineConfigBoolean("showCursorPosition", {
  default: true,
  description: "Display cursor line number and total lines in Discord activity.",
});

editor.defineConfigBoolean("showWorkspace", {
  default: true,
  description: "Display current workspace/project folder name in Discord activity.",
});

const sessionStart = Math.floor(Date.now() / 1000);
let rpcEnabled = true;
let isDirty = false;
let lastSerialized = "";

function getStateFilePath(): string {
  const xdg = editor.getEnv("XDG_RUNTIME_DIR");
  if (xdg) {
    return editor.pathJoin(xdg, "fresh-discord-rpc.json");
  }
  const temp = editor.getEnv("TEMP") || editor.getEnv("TMP") || editor.getEnv("TMPDIR") || "/tmp";
  return editor.pathJoin(temp, "fresh-discord-rpc.json");
}

function isWindows(): boolean {
  const os = (editor.getEnv("OS") || "").toLowerCase();
  return os.includes("windows") || Boolean(editor.getEnv("WINDIR")) || Boolean(editor.getEnv("SystemRoot"));
}

function getDaemonPath(): string {
  // 1. Try plugin directory directly (works regardless of install location)
  try {
    const pluginDir = editor.getPluginDir();
    if (pluginDir) {
      const p = editor.pathJoin(pluginDir, "daemon.py");
      if (editor.fileExists(p)) {
        return p;
      }
    }
  } catch (_) {}

  // 2. Try standard packages directory
  try {
    const pkgDaemon = editor.pathJoin(
      editor.getConfigDir(),
      "plugins",
      "packages",
      "fresh-discord-rpc",
      "daemon.py"
    );
    if (editor.fileExists(pkgDaemon)) {
      return pkgDaemon;
    }
  } catch (_) {}

  return "daemon.py";
}

function ensureDaemonRunning(): void {
  try {
    const daemon = getDaemonPath();
    if (editor.fileExists(daemon)) {
      const pyCmd = isWindows() ? "python" : "python3";
      editor.spawnBackgroundProcess(pyCmd, [daemon]);
    }
  } catch (err: any) {
    editor.debug("Fresh Discord RPC: Daemon spawn notice: " + (err?.message || err));
  }
}

function collectState(): Record<string, unknown> {
  const config = (editor.getPluginConfig() as Record<string, any>) || {};
  const isEnabled = typeof config.enabled === "boolean" ? config.enabled : rpcEnabled;
  const showWs = config.showWorkspace !== false;
  const showCursor = config.showCursorPosition !== false;
  const prefix = config.presencePrefix || "Editing";
  const customClientId = "";

  const activeId = editor.getActiveBufferId();
  const bufferInfo = activeId > 0 ? editor.getBufferInfo(activeId) : null;
  const cursor = editor.getPrimaryCursor();
  const cwd = editor.getCwd() || "";
  
  const pathParts = cwd.split(/[\\/]/).filter(Boolean);
  const workspace = showWs ? (pathParts.length > 0 ? pathParts[pathParts.length - 1] : "Workspace") : "";

  let activeFile = "";
  let filePath = "";
  let language = "";
  let lineCount: number | null = null;
  let cursorLine: number | null = null;
  let modified = false;

  if (bufferInfo && !bufferInfo.is_terminal) {
    const rawName = bufferInfo.name || (bufferInfo.path ? bufferInfo.path.split(/[\\/]/).pop() || "" : "");
    activeFile = (rawName.includes("/") || rawName.includes("\\")) ? rawName.split(/[\\/]/).pop() || rawName : rawName;
    filePath = bufferInfo.path || "";
    language = bufferInfo.language || "";
    lineCount = showCursor ? (bufferInfo.line_count ?? null) : null;
    modified = bufferInfo.modified;
    if (showCursor && cursor && cursor.line !== null && cursor.line !== undefined) {
      cursorLine = cursor.line + 1; // 1-indexed for display
    }
  }

  const buffers = editor.listBuffers() || [];
  const openBuffersCount = buffers.filter((b) => !b.is_terminal && !b.is_virtual).length;

  return {
    enabled: isEnabled,
    cwd: showWs ? cwd : "",
    workspace,
    active_file: activeFile,
    file_path: filePath,
    language,
    cursor_line: cursorLine,
    line_count: lineCount,
    modified,
    open_buffers_count: openBuffersCount,
    activity_prefix: prefix,
    client_id: customClientId,
    session_start: sessionStart,
    updated_at: Math.floor(Date.now() / 1000)
  };
}

function writeStateFile(filePath: string, content: string): boolean {
  try {
    if (typeof editor.replaceFile === "function") {
      const p = typeof editor.localPath === "function" ? editor.localPath(filePath) : filePath;
      if (editor.replaceFile(p, content)) {
        return true;
      }
    }
  } catch (_) {}

  try {
    const p = typeof editor.localPath === "function" ? editor.localPath(filePath) : filePath;
    return editor.writeFile(p, content);
  } catch (_) {}

  return false;
}

let lastFlushTime = 0;

function flushState(force = false): void {
  try {
    const state = collectState();
    const serialized = JSON.stringify(state, null, 2);
    const now = Math.floor(Date.now() / 1000);
    
    // Check if relevant fields changed or if forced or periodic heartbeat
    const compareObj = { ...state, updated_at: 0 };
    const compareStr = JSON.stringify(compareObj);
    
    if (force || compareStr !== lastSerialized || isDirty || (now - lastFlushTime >= 3)) {
      lastSerialized = compareStr;
      lastFlushTime = now;
      isDirty = false;
      const targetPath = getStateFilePath();
      writeStateFile(targetPath, serialized);
    }
  } catch (err: any) {
    editor.debug("Fresh Discord RPC: State flush error: " + (err?.message || err));
  }
}

// Handlers
function onEditorChange(): void {
  flushState(true);
}
registerHandler("discord_rpc_on_change", onEditorChange);

let cursorTimerId: number | null = null;
let lastCursorMoveTime = 0;

function onCursorSettle(): void {
  cursorTimerId = null;
  lastCursorMoveTime = 0;
  flushState(false);
}
registerHandler("discord_rpc_cursor_settle", onCursorSettle);

function onCursorMove(): void {
  isDirty = true;
  const now = Date.now();
  if (!lastCursorMoveTime) {
    lastCursorMoveTime = now;
  }

  if (cursorTimerId !== null) {
    try {
      editor.clearInterval(cursorTimerId);
    } catch (_) {}
    cursorTimerId = null;
  }

  // If user navigates continuously for > 1.5s, trigger flush
  if (now - lastCursorMoveTime >= 1500) {
    lastCursorMoveTime = now;
    flushState(false);
  } else {
    try {
      cursorTimerId = editor.setTimeout(200, "discord_rpc_cursor_settle");
    } catch (_) {
      // Fallback
      flushState(false);
    }
  }
}
registerHandler("discord_rpc_on_cursor", onCursorMove);

function onHeartbeat(): void {
  // Periodic background heartbeat to ensure daemon tracks active session
  flushState(false);
}
registerHandler("discord_rpc_heartbeat", onHeartbeat);

function onToggleRpc(): void {
  rpcEnabled = !rpcEnabled;
  try {
    editor.setSetting("plugins.fresh-discord-rpc.settings.enabled", rpcEnabled);
  } catch (_) {}
  flushState(true);
  editor.setStatus("Discord RPC: " + (rpcEnabled ? "Enabled" : "Disabled"));
}
registerHandler("discord_rpc_toggle", onToggleRpc);

function onConfigChange(): void {
  const config = (editor.getPluginConfig() as Record<string, any>) || {};
  if (typeof config.enabled === "boolean") {
    rpcEnabled = config.enabled;
  }
  flushState(true);
}
registerHandler("discord_rpc_on_config_change", onConfigChange);

function onStatusRpc(): void {
  const state = collectState();
  const file = (state.active_file as string) || "None";
  const statusMsg = `Discord RPC: ${rpcEnabled ? "Active" : "Disabled"} | File: ${file} | Workspace: ${state.workspace}`;
  editor.setStatus(statusMsg);
}
registerHandler("discord_rpc_status", onStatusRpc);

// Hook events
editor.on("ready", "discord_rpc_on_change");
editor.on("config_changed", "discord_rpc_on_config_change");
editor.on("buffer_activated", "discord_rpc_on_change");
editor.on("buffer_deactivated", "discord_rpc_on_change");
editor.on("buffer_closed", "discord_rpc_on_change");
editor.on("after_file_open", "discord_rpc_on_change");
editor.on("after_file_save", "discord_rpc_on_change");
editor.on("after_file_revert", "discord_rpc_on_change");
editor.on("language_changed", "discord_rpc_on_change");
editor.on("cursor_moved", "discord_rpc_on_cursor");

// Register commands
editor.registerCommand("Discord RPC: Toggle", "Toggle Discord Rich Presence", "discord_rpc_toggle", null);
editor.registerCommand("Discord RPC: Status", "Show Discord Rich Presence status", "discord_rpc_status", null);

// Start periodic heartbeat (every 3 seconds)
editor.setInterval(3000, "discord_rpc_heartbeat");

// Ensure daemon is active & perform initial flush
ensureDaemonRunning();
flushState(true);
