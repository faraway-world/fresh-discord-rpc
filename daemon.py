#!/usr/bin/env python3
"""
Fresh Editor - Discord Rich Presence Micro-Daemon
Zero-dependency, pure Python standard library Discord IPC bridge.
Compatible with Linux, macOS, and Windows.
"""

import os
import sys
import time
import json
import uuid
import struct
import socket
import signal
import functools
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# Ensure all prints are unbuffered
print = functools.partial(print, flush=True)

# Default Discord Application ID
# To show "Fresh Editor" in Discord, register a free application at
# https://discord.com/developers/applications and paste its Application ID here.
DEFAULT_CLIENT_ID = "1558908691967778856"
DEFAULT_LOGO_URL = "https://raw.githubusercontent.com/faraway-world/fresh-discord-rpc/main/assets/fresh-editor.png"

# Opcodes for Discord IPC
OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

# Language badge mapping
LANGUAGE_ASSETS = {
    "rust": "rust",
    "rs": "rust",
    "python": "python",
    "py": "python",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "tsx": "typescript",
    "jsx": "javascript",
    "c": "c",
    "h": "c",
    "cpp": "cpp",
    "hpp": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "csharp": "csharp",
    "cs": "csharp",
    "go": "go",
    "html": "html",
    "css": "css",
    "scss": "css",
    "sass": "css",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "markdown": "markdown",
    "md": "markdown",
    "bash": "bash",
    "sh": "bash",
    "zsh": "bash",
    "lua": "lua",
    "java": "java",
    "kotlin": "kotlin",
    "kt": "kotlin",
    "zig": "zig",
    "php": "php",
    "ruby": "ruby",
    "rb": "ruby",
    "swift": "swift",
    "sql": "sql",
    "dockerfile": "docker",
}

def get_state_file_path() -> Path:
    """Determine state file location."""
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.exists(xdg_runtime):
        return Path(xdg_runtime) / "fresh-discord-rpc.json"
    tmp = os.environ.get("TMPDIR") or "/tmp"
    return Path(tmp) / "fresh-discord-rpc.json"

def get_lock_file_path() -> Path:
    """Determine lock file location to ensure a single running daemon."""
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.exists(xdg_runtime):
        return Path(xdg_runtime) / "fresh-discord-rpc.lock"
    tmp = os.environ.get("TMPDIR") or "/tmp"
    return Path(tmp) / "fresh-discord-rpc.lock"

def get_log_file_path() -> Path:
    """Determine log file location."""
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime and os.path.exists(xdg_runtime):
        return Path(xdg_runtime) / "fresh-discord-rpc.log"
    tmp = os.environ.get("TMPDIR") or "/tmp"
    return Path(tmp) / "fresh-discord-rpc.log"

def log(msg: str):
    """Write timestamped log message to stdout and log file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [Fresh Discord RPC] {msg}"
    print(formatted, flush=True)
    try:
        with open(get_log_file_path(), "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def load_user_config() -> Dict[str, Any]:
    """Read user configuration file if present."""
    config_path = Path.home() / ".config" / "fresh" / "discord_rpc.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def acquire_single_instance_lock():
    """Ensure only one instance of the daemon runs."""
    lock_file = get_lock_file_path()
    try:
        import fcntl
        lock_fd = open(lock_file, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(f"{os.getpid()}\n")
        lock_fd.flush()
        return lock_fd
    except (IOError, OSError, ImportError):
        log(f"Another instance is already running (locked {lock_file}). Exiting.")
        sys.exit(0)

def find_discord_ipc_socket() -> Optional[str]:
    """Locate Discord IPC socket across Linux, macOS, and Windows."""
    if sys.platform == "win32":
        for i in range(10):
            pipe_path = rf"\\.\pipe\discord-ipc-{i}"
            if os.path.exists(pipe_path):
                return pipe_path
        return None

    # Unix search paths
    candidates = []
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        candidates.extend([os.path.join(xdg, f"discord-ipc-{i}") for i in range(10)])
        candidates.extend([os.path.join(xdg, "app", "com.discordapp.Discord", f"discord-ipc-{i}") for i in range(10)])
        candidates.extend([os.path.join(xdg, "snap.discord", f"discord-ipc-{i}") for i in range(10)])
    
    tmp = os.environ.get("TMPDIR") or "/tmp"
    candidates.extend([os.path.join(tmp, f"discord-ipc-{i}") for i in range(10)])
    
    uid = os.getuid()
    candidates.extend([f"/run/user/{uid}/discord-ipc-{i}" for i in range(10)])
    candidates.extend([f"/run/user/{uid}/app/com.discordapp.Discord/discord-ipc-{i}" for i in range(10)])

    for path in candidates:
        if os.path.exists(path):
            return path
    return None

class DiscordIPCClient:
    """Pure-Python standard library Discord IPC client."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self.sock: Optional[socket.socket] = None
        self.connected = False

    def connect(self) -> bool:
        """Connect to Discord IPC socket and perform handshake."""
        sock_path = find_discord_ipc_socket()
        if not sock_path:
            return False

        try:
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(2.0)
            self.sock.connect(sock_path)
            
            # Send Opcode 0 (Handshake)
            payload = json.dumps({"v": 1, "client_id": self.client_id}).encode("utf-8")
            header = struct.pack("<II", OP_HANDSHAKE, len(payload))
            self.sock.sendall(header + payload)

            # Read Handshake response
            op, resp = self._read_frame()
            if op == OP_FRAME and resp.get("evt") == "READY":
                self.connected = True
                return True
            self.close()
            return False
        except Exception as e:
            self.close()
            return False

    def _read_frame(self) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """Read a single length-prefixed frame from Discord."""
        if not self.sock:
            return None, None
        try:
            hdr = bytearray()
            while len(hdr) < 8:
                chunk = self.sock.recv(8 - len(hdr))
                if not chunk:
                    return None, None
                hdr.extend(chunk)
            op, length = struct.unpack("<II", hdr)
            buf = bytearray()
            while len(buf) < length:
                chunk = self.sock.recv(min(length - len(buf), 4096))
                if not chunk:
                    break
                buf.extend(chunk)
            data = json.loads(buf.decode("utf-8"))
            return op, data
        except Exception:
            return None, None

    def send_activity(self, activity: Optional[Dict[str, Any]]) -> bool:
        """Send SET_ACTIVITY command."""
        if not self.sock or not self.connected:
            return False
        try:
            frame = {
                "cmd": "SET_ACTIVITY",
                "args": {
                    "pid": os.getpid(),
                    "activity": activity
                },
                "nonce": str(uuid.uuid4())
            }
            payload = json.dumps(frame).encode("utf-8")
            header = struct.pack("<II", OP_FRAME, len(payload))
            self.sock.sendall(header + payload)
            
            # Drain response non-blockingly
            self._read_frame()
            return True
        except Exception:
            self.close()
            return False

    def close(self):
        """Close socket connection cleanly."""
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            finally:
                self.sock = None

class DiscordBridgeDaemon:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.config = load_user_config()
        self.client_id = os.environ.get("FRESH_DISCORD_CLIENT_ID") or self.config.get("client_id") or DEFAULT_CLIENT_ID
        self.activity_prefix = self.config.get("activity_prefix", "Editing")
        
        self.client = DiscordIPCClient(self.client_id)
        self.running = True
        self.last_update_time = 0.0
        self.last_payload: Optional[Dict[str, Any]] = None
        self.pending_payload: Optional[Dict[str, Any]] = None
        self.activity_cleared = False

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        log(f"Received signal {signum}, stopping daemon...")
        self.running = False

    def reload_config(self):
        """Periodically reload config to detect Client ID or setting changes."""
        self.config = load_user_config()
        new_client_id = os.environ.get("FRESH_DISCORD_CLIENT_ID") or self.config.get("client_id") or DEFAULT_CLIENT_ID
        self.activity_prefix = self.config.get("activity_prefix", "Editing")
        
        if new_client_id != self.client_id:
            log(f"Client ID updated to {new_client_id}, reconnecting...")
            self.client.close()
            self.client_id = new_client_id
            self.client = DiscordIPCClient(self.client_id)

    def is_fresh_running(self) -> bool:
        """Check if any fresh process is running."""
        try:
            ppid = os.getppid()
            if ppid > 1:
                try:
                    comm_file = Path(f"/proc/{ppid}/comm")
                    if comm_file.exists() and "fresh" in comm_file.read_text().strip().lower():
                        return True
                except Exception:
                    pass

            import subprocess
            if sys.platform == "win32":
                out = subprocess.check_output(
                    ["tasklist", "/FI", "IMAGENAME eq fresh.exe", "/NH"],
                    stderr=subprocess.DEVNULL
                ).decode("utf-8", errors="ignore")
                return "fresh.exe" in out.lower()
            else:
                res = subprocess.run(
                    ["pgrep", "-x", "fresh"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                return res.returncode == 0 and bool(res.stdout.strip())
        except Exception:
            return False

    def read_state(self) -> Optional[Dict[str, Any]]:
        """Read state file written by Fresh plugin."""
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError):
            return None

    def build_activity(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build Discord activity dictionary from Fresh state."""
        if not state.get("enabled", True):
            return None

        if not self.is_fresh_running():
            return None

        updated_at = state.get("updated_at", 0)
        now = time.time()
        
        # Consider stale if state was not updated in 300 seconds
        if now - updated_at > 300.0:
            return None

        active_file = state.get("active_file", "")
        workspace = state.get("workspace", "")
        cwd = state.get("cwd", "")
        folder_dir = cwd or workspace
        language = state.get("language", "").lower()
        line = state.get("cursor_line")
        line_count = state.get("line_count")
        modified = state.get("modified", False)
        session_start = state.get("session_start", int(now))

        state_prefix = state.get("activity_prefix")
        active_prefix = state_prefix or self.activity_prefix

        state_client_id = state.get("client_id")
        target_client_id = state_client_id or os.environ.get("FRESH_DISCORD_CLIENT_ID") or self.config.get("client_id") or DEFAULT_CLIENT_ID
        if target_client_id != self.client_id:
            log(f"Client ID switched to {target_client_id}, reconnecting...")
            self.client.close()
            self.client_id = target_client_id
            self.client = DiscordIPCClient(self.client_id)

        ext = ""
        if active_file and "." in active_file:
            ext = active_file.rsplit(".", 1)[-1].lower()

        custom_logo = self.config.get("large_image")
        icon = custom_logo or DEFAULT_LOGO_URL
        lang_display = language.capitalize() if language else (ext.upper() if ext else "Code")

        if active_file and active_file != "[No Name]":
            line_str = ""
            if line is not None and line_count is not None and line_count > 0:
                line_str = f" [Line:{line}/Total:{line_count}]"
            elif line is not None:
                line_str = f" [Line:{line}]"
                
            mod_flag = " *" if modified else ""
            details = f"{active_prefix} {active_file}{mod_flag}{line_str}"
            state_text = f"Workspace: {folder_dir}" if folder_dir else "In Fresh Editor"
            large_text = f"Fresh Editor - {lang_display}"
        else:
            details = "Idling in Fresh"
            state_text = f"Workspace: {folder_dir}" if folder_dir else "Fresh Editor"
            large_text = "Fresh Editor"

        small_image = None
        small_text = None

        activity: Dict[str, Any] = {
            "type": 0,  # Playing
            "details": details[:128],
            "state": state_text[:128],
            "assets": {
                "large_image": icon,
                "large_text": large_text[:128]
            },
            "timestamps": {
                "start": int(session_start)
            },
            "buttons": [
                {"label": "Fresh Editor", "url": "https://github.com/sinelaw/fresh"}
            ]
        }
        if small_image:
            activity["assets"]["small_image"] = small_image
            activity["assets"]["small_text"] = (small_text or "")[:128]

        return activity

    def update(self, activity: Optional[Dict[str, Any]]):
        """Update activity with rate-limiting."""
        now = time.time()

        if activity is None:
            if self.client.connected and not self.activity_cleared:
                self.client.send_activity(None)
                self.activity_cleared = True
                self.last_payload = None
                self.pending_payload = None
                log("Activity cleared.")
            return

        if self.last_payload == activity:
            self.pending_payload = None
            return

        # Discord rate-limit: 15 seconds
        elapsed = now - self.last_update_time
        if elapsed < 15.0 and self.last_payload is not None:
            self.pending_payload = activity
            return

        if self.client.send_activity(activity):
            self.last_update_time = now
            self.last_payload = activity
            self.pending_payload = None
            self.activity_cleared = False
            log(f"Updated: {activity.get('details')} | {activity.get('state')}")
        else:
            log("Failed to send activity. Will reconnect...")
            self.client.close()

    def run(self):
        """Main loop."""
        log(f"Micro-daemon started (PID {os.getpid()}).")
        log(f"Watching: {self.state_file}")
        
        reconnect_cooldown = 0.0
        config_check_time = 0.0
        fresh_offline_time: Optional[float] = None

        while self.running:
            now = time.time()

            # If Fresh has exited, track offline duration and shut down after 30s of inactivity
            if not self.is_fresh_running():
                if fresh_offline_time is None:
                    fresh_offline_time = now
                elif now - fresh_offline_time > 30.0:
                    log("Fresh editor is not running. Daemon exiting cleanly.")
                    self.running = False
            else:
                fresh_offline_time = None

            if now - config_check_time > 5.0:
                self.reload_config()
                config_check_time = now

            if not self.client.connected:
                if now >= reconnect_cooldown:
                    if self.client.connect():
                        log(f"Connected to Discord IPC (Client ID: {self.client_id}).")
                        reconnect_cooldown = 0.0
                    else:
                        reconnect_cooldown = now + 5.0

            if self.client.connected:
                state = self.read_state()
                activity = self.build_activity(state) if state else None

                if activity is None:
                    # RPC disabled or stale: clear any pending update and send None
                    self.pending_payload = None
                    self.update(None)
                elif self.pending_payload and (now - self.last_update_time >= 15.0):
                    # Rate-limit window passed: send the latest activity
                    self.update(activity)
                else:
                    self.update(activity)

            time.sleep(1.0)

        # Clean shutdown
        if self.client.connected:
            self.client.send_activity(None)
            self.client.close()
        log("Micro-daemon stopped cleanly.")

def main():
    _lock = acquire_single_instance_lock()
    state_file = get_state_file_path()
    daemon = DiscordBridgeDaemon(state_file)
    daemon.run()

if __name__ == "__main__":
    main()
