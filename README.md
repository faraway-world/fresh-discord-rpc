<div align="center">

# fresh-discord-rpc

**Zero-configuration, lightweight Discord Rich Presence (RPC) integration for the [Fresh](https://github.com/sinelaw/fresh) terminal text editor.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)]()
[![Runtime](https://img.shields.io/badge/Runtime-Python%203.8%2B%20(Stdlib%20Only)-yellow.svg)]()
[![Editor](https://img.shields.io/badge/Editor-Fresh%20%E2%89%A50.4.0-brightgreen.svg)](https://github.com/sinelaw/fresh)

---

## Overview

`fresh-discord-rpc` is an automated, zero-dependency Rich Presence integration designed for the [Fresh](https://github.com/sinelaw/fresh) terminal text editor. It provides real-time workspace and buffer activity directly to Discord, while respecting system resource constraints and Discord rate limits.

<p align="center">
  <img width="537" height="222" alt="image" src="https://github.com/user-attachments/assets/a169cdaa-e7d9-4680-8326-9d4ced20eaa1" />
</p>

The integration operates out of the box with zero external package installations (`pip`, virtual environments, or system services are not required) and cleans up its presence instantaneously upon editor termination.
</div>

---

## Key Features

- **Plug-and-Play Integration**: Functions immediately upon cloning into the Fresh packages directory. No package installations, external daemons, or background service configurations required.
- **Zero External Dependencies**: The background IPC micro-daemon utilizes Python's standard library (`socket`, `struct`, `json`, `fcntl`), eliminating runtime packaging overhead.
- **Granular Activity Tracking**: Broadcasts active filename, dirty/modified buffer state (`*`), 1-indexed cursor line, total line count, and working directory path:
  ```text
  Editing daemon.py * [Line:42/Total:443]
  Workspace: /home/user/projects/fresh-discord-rpc
  ```
- **Instant Teardown & Lifecycle Awareness**: Continuously monitors the parent editor process and socket state. Presence is cleared within 1 second of closing Fresh, with automatic daemon shutdown after 30 seconds of editor inactivity.
- **Sandboxed Bridge Architecture**: Overcomes embedded JavaScript sandbox limitations by decoupling event telemetry from raw IPC socket communication.
- **Adaptive Token Bucket Rate Limiting**: Implements a token bucket algorithm (5-request burst capacity with 4-second refill) in strict compliance with Discord's IPC rate limits. Active file switches dispatch near-instantly (<250ms), while cursor line updates are throttled to a smooth 2-second pacing with token reserves to prevent event starvation.
- **Command Palette Control**: Provides native editor commands to inspect status and toggle Rich Presence at runtime.

---

## Architecture

Fresh executes plugins within an isolated **QuickJS (ES2020)** engine. Because embedded JavaScript environments cannot interface directly with raw Unix Domain Sockets or Windows Named Pipes, `fresh-discord-rpc` implements a decoupled, hybrid IPC bridge.

```
┌────────────────────────────────────────────────────────┐
│                   Fresh Text Editor                    │
│                                                        │
│  fresh-discord-rpc.ts (QuickJS)                        │
│  ├─ Hooks: buffer_activated, cursor_moved, save, etc.  │
│  ├─ Settings: defineConfig UI integration              │
│  └─ Writes state atomically to runtime JSON file       │
└──────────────────────────┬─────────────────────────────┘
                           │ Atomic JSON Flush
                           ▼
┌────────────────────────────────────────────────────────┐
│        $XDG_RUNTIME_DIR/fresh-discord-rpc.json         │
└──────────────────────────┬─────────────────────────────┘
                           │ 250ms Poll & Token Bucket Dispatch
                           ▼
┌────────────────────────────────────────────────────────┐
│           daemon.py (Pure Python 3 Stdlib)             │
│                                                        │
│  ├─ Single-instance mutual exclusion lock (flock)      │
│  ├─ Parent process monitoring (PID / comm check)       │
│  ├─ Token bucket rate limiter (2s cursor pacing)       │
│  └─ Length-prefixed binary frames (Opcode 0 / Opcode 1)│
└──────────────────────────┬─────────────────────────────┘
                           │ Unix Domain Socket / Named Pipe
                           ▼
┌────────────────────────────────────────────────────────┐
│              Discord Desktop Client (IPC)              │
│       /run/user/<uid>/discord-ipc-0 or \\.\pipe\...    │
└────────────────────────────────────────────────────────┘
```

1. **Plugin Core (`fresh-discord-rpc.ts`)**: Subscribes to editor lifecycle and buffer events, manages user preferences via Fresh's native settings framework, debounces rapid cursor changes, and periodically writes atomic editor state to `$XDG_RUNTIME_DIR/fresh-discord-rpc.json`.
2. **Micro-Daemon (`daemon.py`)**: A single-instance background worker spawned automatically by the plugin. It establishes an `AF_UNIX` (or Windows Named Pipe) stream to Discord, formats activity payloads, handles connection recovery, and ensures immediate presence teardown upon editor exit.

---

## Installation

### Method 1: Fresh Package Manager (Recommended)

Install directly from inside Fresh using the Command Palette:

1. Press `Ctrl+P` (or your mapped Command Palette shortcut).
2. Execute **`Package: Install from URL`**.
3. Enter repository URL:
   ```text
   https://github.com/faraway-world/fresh-discord-rpc
   ```

### Method 2: Git Clone (Manual)

Clone this repository into your Fresh packages directory:

```bash
git clone https://github.com/faraway-world/fresh-discord-rpc.git ~/.config/fresh/plugins/packages/fresh-discord-rpc
```

### Verification
Open any file with Fresh:
```bash
fresh path/to/file.ext
```
Rich Presence will initialize automatically, and your Discord activity will display **Playing Fresh Editor**.

---

## Editor Settings & Configuration

`fresh-discord-rpc` is integrated directly into Fresh Editor's native graphical Settings UI (`Ctrl+P` &rarr; `Open Settings` &rarr; **Plugins** &rarr; **fresh-discord-rpc**):

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enabled` | `boolean` | `true` | Toggle Discord Rich Presence broadcast on or off. |
| `presencePrefix` | `string` | `"Editing"` | Verb prefix displayed before active filename (e.g., `Editing`, `Viewing`, `Working on`). |
| `showCursorPosition` | `boolean` | `true` | Display active line number and total buffer line count. |
| `showWorkspace` | `boolean` | `true` | Display active workspace or project folder name. |

Settings can also be configured programmatically in `~/.config/fresh/config.json`:

```json
{
  "plugins": {
    "fresh-discord-rpc": {
      "enabled": true,
      "settings": {
        "enabled": true,
        "presencePrefix": "Editing",
        "showCursorPosition": true,
        "showWorkspace": true
      }
    }
  }
}
```

---

## Editor Commands

The plugin exposes commands via the Fresh Command Palette (`Ctrl+P` or custom binding):

| Command | Action |
| :--- | :--- |
| `Discord RPC: Toggle` | Toggles Rich Presence broadcast on or off dynamically during a session. |
| `Discord RPC: Status` | Prints current connection status, active file, and workspace path to the status bar. |

---

## Configuration

The extension functions without any configuration. To customize defaults, create a configuration file at `~/.config/fresh/discord_rpc.json`:

```json
{
  "client_id": "1558908691967778856",
  "activity_prefix": "Editing",
  "large_image": "https://raw.githubusercontent.com/faraway-world/fresh-discord-rpc/main/assets/fresh-editor.png"
}
```

### Configuration Options

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `client_id` | `string` | `"1558908691967778856"` | Discord Application ID. Can also be overridden via the `FRESH_DISCORD_CLIENT_ID` environment variable. |
| `activity_prefix` | `string` | `"Editing"` | Text prefix prepended to the active filename (e.g., `Editing`, `Reviewing`, `Developing`). |
| `large_image` | `string` | Official Logo URL | Image key or HTTPS URL for the primary presence badge. Defaults to the official Fresh Editor logo hosted on GitHub. |

---

## System Requirements

- **Editor**: [Fresh](https://github.com/sinelaw/fresh) v0.4.0 or higher.
- **Python**: Python 3.8+ (standard library only; no virtual environment or `pip` dependencies).
- **Discord**: Discord Desktop client running on the local machine with an active IPC socket:
  - Linux: `$XDG_RUNTIME_DIR/discord-ipc-0` or `/run/user/<uid>/discord-ipc-0`
  - macOS: `$TMPDIR/discord-ipc-0`
  - Windows: `\\.\pipe\discord-ipc-0`

---

## Troubleshooting

### Activity Does Not Appear in Discord
1. **Verify Discord Client**: Ensure the official Discord desktop client is running locally under the same user session.
2. **Verify IPC Socket**: On Linux, verify that the IPC socket is present:
   ```bash
   ls -l /run/user/$UID/discord-ipc-*
   ```
3. **Inspect Daemon Log**: Run the daemon manually in a terminal to inspect output:
   ```bash
   python3 ~/.config/fresh/plugins/packages/fresh-discord-rpc/daemon.py
   ```

### Immediate Teardown
If your presence persists after exiting Fresh, ensure your user has permissions to execute `pgrep` on your platform. The daemon monitors the host process tree and clears presence within 1 second of the parent process exiting.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

