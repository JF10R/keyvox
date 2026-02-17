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
- Backend capability and validation endpoints for guided settings UIs:
  - `get_capabilities`
  - `list_audio_devices`
  - `validate_model_config`
- Background model download endpoint + events:
  - `download_model`
  - `model_download` + `model_download_progress` (status + progress + byte counters)
- Storage management:
  - `get_storage_status`
  - `set_storage_root` with destination free-space precheck
  - background `storage_migration` + `storage_updated` events
- Live state panel (`idle`, `recording`, `processing`)
- Latest transcription panel
- Settings controls for hotkey, model, audio, text insertion, and storage root
- Model readiness indicators, required/free space hints, and download progress bars
- Tray tooltip status updates (ready/loading) and native storage folder picker
- SQLite-backed history browsing, search, delete, clear, and export
- Hardware detection display (GPU name + VRAM) and VRAM-based model recommendation badges on selectors
- Dark/light theme toggle with OS preference detection and `localStorage` persistence
- WCAG 2.1 AA accessibility: skip navigation, focus-visible rings, ARIA live regions, form labels,
  validation error associations (`aria-describedby`), keyboard-navigable dictionary table, dismissible toasts

## Theme

The UI supports dark and light themes. On first load, the OS `prefers-color-scheme` preference is
used; subsequent launches use the last saved preference from `localStorage`.

The toggle button (☾/☀) is in the top-right of the header. Theme is stored under the key
`keyvox-theme` as `"dark"` or `"light"`.

Implementation: CSS custom properties on `:root` + overrides under `[data-theme="dark"]` on `<html>`.
Transitions are applied only to structural elements (`background-color`, `border-color`, `color`)
to avoid interfering with button/animation timing.

## Accessibility

The UI targets WCAG 2.1 AA compliance:

- **Skip link** — `Skip to content` appears on focus for keyboard users
- **Focus ring** — `:focus-visible` outline on all interactive elements in accent color
- **ARIA live regions** — engine state (`aria-live="polite"`), toast notifications (`role="log"`),
  validation errors (`role="alert"`)
- **Form labels** — all inputs and selects have explicit `<label>` associations or `aria-label`
- **Validation errors** — model config fields use `aria-invalid` + `aria-describedby` to
  programmatically associate errors with their inputs
- **Dictionary table** — replacement cell has `role="button"`, `tabindex="0"`, Enter/Space handler;
  column headers have `scope="col"`
- **Progress elements** — `aria-label` with percentage on all `<progress>` bars
- **Dismissible toasts** — each notification has a `×` close button
- **`type="button"`** — all standalone buttons to prevent accidental form submission

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
