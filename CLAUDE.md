# Keyvox - Project Conventions

## What this repo is

Local push-to-talk speech-to-text:
- Hold hotkey
- Speak
- Release
- Text is inserted into the active app

Backends are pluggable (`faster-whisper`, `qwen-asr`, `qwen-asr-vllm`).

## Architecture

```text
keyvox/
  __main__.py         # CLI entry point: --setup / --headless / --server
  config.py           # TOML load/save + platform-aware discovery
  config_reload.py    # Runtime config polling
  recorder.py         # Audio capture (sounddevice)
  hotkey.py           # Push-to-talk listener only (enqueues audio, no transcription)
  pipeline.py         # Worker thread: transcription → dictionary → text insertion → output
  text_insertion.py   # Context-aware spacing/capitalization/url normalization
  dictionary.py       # Dictionary corrections
  history.py          # SQLite transcription persistence
  storage.py          # Unified storage root management + migration
  hardware.py         # GPU detection + VRAM-based model recommendation
  server.py           # WebSocket protocol server over localhost
  backends/           # Transcriber backend factory + implementations
apps/desktop/
  src/                # Svelte desktop UI
  src-tauri/          # Tauri host + backend process manager
```

## Runtime Modes

- `keyvox`: default local CLI runtime (push-to-talk + local insertion)
- `keyvox --headless`: explicit alias for same local CLI runtime
- `keyvox --server [--port N]`: backend-only WebSocket engine mode

## Key Decisions

- `faster-whisper` stays default backend on NVIDIA; now optional dep (`[nvidia]` extra, not in base install).
- `torch` stays unmanaged in project deps (user installs matching CUDA build).
- Config lookup order: CWD first, then platform config dir.
- Single-instance guard uses `pywin32` when installed; otherwise no-op fallback.
- Dictionary/text insertion are hot-reloaded at runtime.
- Server protocol uses request/response envelope with `request_id` correlation.
- `storage.py` manages unified storage root with automatic migration and free-space precheck.
- Capabilities endpoint (`get_capabilities`) drives UI validation for model/backend/device/compute selectors.
- Desktop model selectors are constrained `<select>` dropdowns (not free-text), reactively filtered by capabilities.
- Dictionary CRUD is managed via desktop UI (table with inline edit) backed by server commands.
- Background job guards disable config inputs during model download or storage migration.
- `hardware.py` detects GPU at server startup; `get_capabilities` exposes hardware info and VRAM-based model recommendation.
- Desktop UI shows GPU info and recommendation badges on model selectors.
- Transcription runs on a dedicated worker thread (`pipeline.py`); the pynput listener thread only enqueues audio (<1ms), preventing missed keypresses during GPU inference.

## Dependency Notes

| Dependency | Purpose |
|---|---|
| `sounddevice` | Microphone capture |
| `pynput` | Global hotkey listener + key simulation |
| `pyperclip` | Clipboard access |
| `numpy` | Audio arrays |
| `faster-whisper` (optional `[nvidia]`) | NVIDIA ASR backend |
| `pywin32` (optional `[singleton]`) | Windows single-instance mutex |
| `websockets` (optional `[server]`) | Server mode transport |

## Development

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -e ".[nvidia,singleton,server]"
keyvox --setup
keyvox
```

Desktop app:

```bash
cd apps/desktop
npm install
npm run tauri dev
```

## Testing

```bash
python -m pytest -q
python -m pytest --cov=keyvox --cov-report=term-missing -q
```

See `docs/testing.md` for suite scope.

## Conventions

- Python 3.11+ (`tomllib` stdlib).
- Favor small, explicit implementations over abstraction-heavy code.
- Avoid hardcoded user paths; use config/platform discovery.
- Runtime logs use text markers (`[INFO]`, `[OK]`, `[WARN]`, `[ERR]`).
