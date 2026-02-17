# Keyvox Desktop

Modern Tauri + Svelte desktop UI for Keyvox.

## Run

```bash
npm install
npm run doctor
npm run tauri dev
```

Prerequisites:
- Node.js 20+
- Rust toolchain (`rustup`, `cargo`, `rustc`)
- MSVC C++ toolchain (`link.exe`) via Visual Studio Build Tools / Community
- Windows SDK (`kernel32.lib`) version 10.0.18362+
- `keyvox` available on `PATH` (or set a full path in `Backend Command`)
  - Typical user install path: `%APPDATA%\\Python\\Python313\\Scripts`

## Backend integration

- Uses `backend_preflight`, `start_backend`, `stop_backend`, `backend_status` Tauri commands
- Connects to existing `keyvox --server` first, then spawns managed backend if needed
- Stops backend on app exit only when this desktop instance started it
- Protocol contract is defined by `keyvox/server.py`
