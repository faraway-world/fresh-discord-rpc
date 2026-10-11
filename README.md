# fresh-discord-rpc 🎮

> **Plug & Play Discord Rich Presence (RPC) integration for the [Fresh](https://getfresh.dev) terminal text editor.**

Zero configuration. Zero external dependencies. Just clone and start editing.

---

## ✨ Features

- ⚡ **Plug & Play**: Works immediately upon cloning. No virtual environments, no `pip install`, and no background service setup needed.
- 🚀 **Zero External Dependencies**: The background micro-daemon is written entirely using the **Python standard library** (`socket`, `struct`, `json`).
- 📁 **Active File & Workspace**: Displays current workspace folder directory and active file (e.g., `Editing main.rs [Line:42/Total:180]` | `Workspace: /home/user/project`).
- 🎯 **Line & Status Tracking**: Live line number, total line count, and `*` indicator when files have unsaved changes.
- 🎨 **Language Icons**: Detects file type and displays appropriate language badges (Rust, Python, TypeScript, Go, C++, etc.).
- ⏱️ **Elapsed Session Timer**: Accurate live timer showing how long you've been working.
- 🤖 **Auto-Daemon Management**: The Fresh plugin automatically launches and manages the lightweight daemon process behind the scenes.
- ⌨️ **Command Palette Integration**:
  - `Discord RPC: Toggle` — enable or disable Rich Presence on demand.
  - `Discord RPC: Status` — display current connection and buffer state in the status bar.

---

## 📦 Installation

To install, simply clone this repository into your Fresh plugins package directory:

```bash
git clone https://github.com/YOUR_USERNAME/fresh-discord-rpc.git ~/.config/fresh/plugins/packages/fresh-discord-rpc
```

That's it! Launch Fresh and your Discord Rich Presence will automatically activate:

```bash
fresh <your-file>
```

---

## 🛠️ How It Works

Fresh plugins run inside an embedded **QuickJS (ES2020)** engine, which is sandboxed and does not support raw Unix stream sockets. Discord RPC requires an open, persistent Unix domain socket connection to `$XDG_RUNTIME_DIR/discord-ipc-0`.

`fresh-discord-rpc` solves this with an ultra-lightweight hybrid bridge:
1. **Fresh Plugin (`plugin.ts`)**: Collects editor events (`buffer_activated`, `cursor_moved`, `after_file_save`, etc.) and serializes atomic editor state into `$XDG_RUNTIME_DIR/fresh-discord-rpc.json`.
2. **Embedded Micro-Daemon (`daemon.py`)**: A small, zero-dependency Python script that maintains the persistent IPC connection to Discord, applies 15-second rate limiting, and cleans up presence when the editor closes.

---

## ⚙️ Configuration (Optional)

By default, the plugin works out of the box.

If you would like to customize your Discord presence, you can create `~/.config/fresh/discord_rpc.json`:

```json
{
  "client_id": "YOUR_DISCORD_APPLICATION_ID",
  "activity_prefix": "Editing"
}
```

### Options:
| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `client_id` | `string` | Built-in | Custom Discord Application ID from the Developer Portal. |
| `activity_prefix` | `string` | `"Editing"` | Status prefix shown before the active file (e.g. `"Editing"`, `"Coding"`, `"Hacking on"`). |

---

## 🏷️ Setting Up Your Own Application Name on Discord

In Discord's Rich Presence system, the bold application title is tied directly to the **Discord Application Name** on Discord's Developer Portal.

If you maintain this repository or want it to display your own custom name (like **Fresh Editor**):

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** and enter the name (e.g., `Fresh Editor` or `Coding in Fresh`).
3. Copy your **Application ID** from the *General Information* page.
4. Replace `DEFAULT_CLIENT_ID` in `daemon.py` with your new Application ID (or put it in `~/.config/fresh/discord_rpc.json`).
5. Anyone who uses your repo will automatically see that name in Discord!

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
