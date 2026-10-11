// Fresh Discord Rich Presence Plugin
// Connects Fresh editor to Discord via the local IPC micro-daemon

const editor = getEditor();

const sessionStart = Math.floor(Date.now() / 1000);
let rpcEnabled = true;
let isDirty = false;
let lastSerialized = "";

function getStateFilePath(): string {
  const xdg = editor.getEnv("XDG_RUNTIME_DIR");
  if (xdg) {
    return editor.pathJoin(xdg, "fresh-discord-rpc.json");
  }
  return "/tmp/fresh-discord-rpc.json";
}

function getDaemonPath(): string {
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
  const scriptsDaemon = "/home/hikari/Scripts/fresh_rpc.py";
  if (editor.fileExists(scriptsDaemon)) {
    return scriptsDaemon;
  }
  return pkgDaemon;
}

function ensureDaemonRunning(): void {
  try {
    const daemon = getDaemonPath();
    if (editor.fileExists(daemon)) {
      editor.spawnBackgroundProcess("python3", [daemon]);
    }
  } catch (err: any) {
    editor.debug("Fresh Discord RPC: Daemon spawn notice: " + (err?.message || err));
  }
}

function collectState(): Record<string, unknown> {
  const activeId = editor.getActiveBufferId();
  const bufferInfo = activeId > 0 ? editor.getBufferInfo(activeId) : null;
  const cursor = editor.getPrimaryCursor();
  const cwd = editor.getCwd() || "";
  
  const pathParts = cwd.split("/").filter(Boolean);
  const workspace = pathParts.length > 0 ? pathParts[pathParts.length - 1] : "Workspace";

  let activeFile = "";
  let filePath = "";
  let language = "";
  let lineCount: number | null = null;
  let cursorLine: number | null = null;
  let modified = false;

  if (bufferInfo && !bufferInfo.is_terminal) {
    activeFile = bufferInfo.name || (bufferInfo.path ? bufferInfo.path.split("/").pop() || "" : "");
    filePath = bufferInfo.path || "";
    language = bufferInfo.language || "";
    lineCount = bufferInfo.line_count ?? null;
    modified = bufferInfo.modified;
    if (cursor && cursor.line !== null) {
      cursorLine = cursor.line + 1; // 1-indexed for display
    }
  }

  const buffers = editor.listBuffers() || [];
  const openBuffersCount = buffers.filter((b) => !b.is_terminal && !b.is_virtual).length;

  return {
    enabled: rpcEnabled,
    cwd,
    workspace,
    active_file: activeFile,
    file_path: filePath,
    language,
    cursor_line: cursorLine,
    line_count: lineCount,
    modified,
    open_buffers_count: openBuffersCount,
    session_start: sessionStart,
    updated_at: Math.floor(Date.now() / 1000)
  };
}

function flushState(force = false): void {
  try {
    const state = collectState();
    const serialized = JSON.stringify(state, null, 2);
    
    // Check if relevant fields changed or if forced
    const compareObj = { ...state, updated_at: 0 };
    const compareStr = JSON.stringify(compareObj);
    
    if (force || compareStr !== lastSerialized || isDirty) {
      lastSerialized = compareStr;
      isDirty = false;
      const targetPath = getStateFilePath();
      editor.writeFile(targetPath, serialized);
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

function onCursorMove(): void {
  isDirty = true;
}
registerHandler("discord_rpc_on_cursor", onCursorMove);

function onHeartbeat(): void {
  // Update heartbeat timestamp & flush debounced cursor edits
  flushState(isDirty);
}
registerHandler("discord_rpc_heartbeat", onHeartbeat);

function onToggleRpc(): void {
  rpcEnabled = !rpcEnabled;
  flushState(true);
  editor.setStatus("Discord RPC: " + (rpcEnabled ? "Enabled" : "Disabled"));
}
registerHandler("discord_rpc_toggle", onToggleRpc);

function onStatusRpc(): void {
  const state = collectState();
  const file = (state.active_file as string) || "None";
  const statusMsg = `Discord RPC: ${rpcEnabled ? "Active" : "Disabled"} | File: ${file} | Workspace: ${state.workspace}`;
  editor.setStatus(statusMsg);
}
registerHandler("discord_rpc_status", onStatusRpc);

// Hook events
editor.on("ready", "discord_rpc_on_change");
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
