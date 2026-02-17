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
  hotkey.py           # Push-to-talk runtime + paste flow
  text_insertion.py   # Context-aware spacing/capitalization/url normalization
  dictionary.py       # Dictionary corrections
  history.py          # SQLite transcription persistence
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

- `faster-whisper` stays default backend on NVIDIA.
- `torch` stays unmanaged in project deps (user installs matching CUDA build).
- Config lookup order: CWD first, then platform config dir.
- Single-instance guard uses `pywin32` when installed; otherwise no-op fallback.
- Dictionary/text insertion are hot-reloaded at runtime.
- Server protocol uses request/response envelope with `request_id` correlation.

## Dependency Notes

| Dependency | Purpose |
|---|---|
| `faster-whisper` | Default ASR backend |
| `sounddevice` | Microphone capture |
| `pynput` | Global hotkey listener + key simulation |
| `pyperclip` | Clipboard access |
| `numpy` | Audio arrays |
| `pywin32` (optional) | Windows single-instance mutex |
| `websockets` (optional) | Server mode transport |

## Development

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -e ".[singleton,server]"
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
