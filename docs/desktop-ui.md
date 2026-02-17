# Keyvox Desktop UI (Tauri + Svelte)

This app is a production-oriented desktop interface for Keyvox, backed by `keyvox --server` over WebSocket.

## Location

- Frontend + app shell: `apps/desktop/`
- Tauri Rust backend manager: `apps/desktop/src-tauri/`

## Features implemented

- Backend process lifecycle controls (`start_backend`, `stop_backend`, `backend_status`)
- Backend preflight validation (`backend_preflight`) before spawn attempts
- WebSocket connection management with request/response command handling
- Connect-first startup strategy: attach to existing backend before spawning one
- Managed backend ownership: app only auto-stops backends it launched
- Bounded reconnect with backoff and manual override when retries are exhausted
- Live state panel (`idle`, `recording`, `processing`)
- Latest transcription panel
- Settings controls for hotkey, model, audio, and text insertion toggles
- SQLite-backed history browsing, search, delete, clear, and export

## Dev setup

From `apps/desktop/`:

```bash
npm install
npm run doctor
npm run tauri dev
```

Prerequisites:
- Node.js 20+
- Rust toolchain (`rustup`, `cargo`, `rustc`) for Tauri host build
- MSVC C++ linker (`link.exe`) from Visual Studio Build Tools / Community
- Windows SDK (`kernel32.lib`) version 10.0.18362+
- WebView2 runtime (Windows)

If the backend binary is not on your PATH, set a command in the UI `Backend Command` field (for example, full path to `keyvox`).

## Protocol model

- Commands are sent as JSON with `type` and `request_id`
- Responses are `type: "response"` with `ok: true/false`
- Asynchronous events are delivered as typed event messages (`state`, `transcription`, `history_appended`, etc.)

See `keyvox/server.py` for the canonical command and event contract.
