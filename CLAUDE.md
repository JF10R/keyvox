# KeyVox — Project Conventions

## What is this?

Local push-to-talk speech-to-text: hold hotkey, speak, release, text appears in active window. GPU-accelerated via faster-whisper (CTranslate2) or whisper.cpp (Vulkan/CPU). Python package, not an EXE (CUDA version flexibility).

## Architecture

```
keyvox/
  __main__.py      # CLI entry point (argparse), single-instance check
  config.py        # TOML config loading/saving, platform-aware paths
  recorder.py      # AudioRecorder — sounddevice InputStream wrapper
  transcriber.py   # Transcriber — faster-whisper model wrapper
  hotkey.py        # HotkeyManager — pynput listener, paste via Ctrl+V
  setup_wizard.py  # Interactive --setup: GPU detect, mic list, model recommend
```

## Key decisions

- **faster-whisper** as default backend — avoids torchcodec/pyannote errors; other backends pluggable via Protocol
- **Default model:** `large-v3-turbo` (distilled, fast, near large-v3 quality)
- **torch not in dependencies** — users install the right version for their CUDA
- **No emojis in output** — plain markers: `[INFO]`, `[OK]`, `[REC]`, `[ERR]`, `[WARN]`
- **Config lookup order:** CWD → platform config dir (APPDATA / XDG / Library)
- **Single instance:** win32event.CreateMutex with ImportError fallback

## Platform support

- **Windows:** primary target, fully functional
- **Linux/macOS:** planned — core pipeline is cross-platform, but hotkey/paste behavior needs testing and adaptation

## Stack

| Dependency | Purpose |
|-----------|---------|
| `faster-whisper` (optional) | Whisper inference — NVIDIA/CUDA (CTranslate2 backend) |
| `pywhispercpp` (optional) | Whisper inference — AMD/CPU (whisper.cpp/ggml backend) |
| `sounddevice` | Mic capture (PortAudio) |
| `pynput` | Global hotkey + simulated paste |
| `pyperclip` | Clipboard |
| `numpy` | Audio array handling |
| `pywin32` (optional) | Single-instance mutex on Windows |

## Development

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -e ".[singleton]"
keyvox --setup
keyvox
```

## Conventions

- Python 3.11+ (uses `tomllib` from stdlib)
- Minimal dependencies — no unnecessary abstractions
- Config via TOML, not CLI flags (CLI only has `--setup`)
- Hardcoded user paths are a bug — always use empty defaults or platform detection

## Architecture Decisions (v0.2+)

### UI Framework: PySide6
- LGPL license, `QSystemTrayIcon` built-in, PyInstaller hooks, cross-platform
- Key components: `QSystemTrayIcon`, `QMainWindow`, `QThread` + Signal/Slot for non-blocking GPU work
- Added as optional dependency: `[project.optional-dependencies] gui = ["PySide6>=6.6.0"]`
- Entry point: `keyvox` launches GUI by default, `keyvox --headless` for CLI-only

### Transcription History: SQLite
- `sqlite3` stdlib — zero dependencies
- Stored in platform config dir alongside `config.toml`
- Schema: `id, timestamp, text, duration_seconds, model_used`

### Dictionary / Word Corrections
- TOML section `[dictionary]` or separate `dictionary.toml`
- Key-value: `{"whatsapp" = "WhatsApp", "github" = "GitHub"}`
- Post-processing after transcription (case-insensitive match, preserve word boundaries)

### Multi-Backend Transcriber (v0.3)

The transcriber layer uses a **model-agnostic backend abstraction** so the inference engine can be swapped at runtime without touching the rest of the app.

**Design principles:**
- **Protocol, not base class** — `TranscriberBackend(Protocol)` with one method: `transcribe(audio_array: np.ndarray) -> str`
- **Model-agnostic** — the Protocol doesn't assume Whisper. Any ASR engine (Conformer, Wav2Vec2, cloud API) can implement it
- **Factory pattern** — `create_transcriber(config)` picks the backend based on `config["model"]["backend"]`
- **Auto-detection** — `backend = "auto"` detects GPU vendor and picks the best available engine
- **Lazy imports** — backend dependencies imported only when selected (no hard dep on any engine)

**Backend implementations:**
- `faster_whisper.py` — NVIDIA GPUs via CTranslate2 (current `transcriber.py` logic, moved here)
- `whisper_cpp.py` — AMD/Intel/CPU via whisper.cpp (Vulkan for GPU, optimized CPU fallback)
- Future: any ASR engine that implements `transcribe(np.ndarray) -> str`

**Config:**
```toml
[model]
backend = "auto"  # "auto", "faster-whisper", "whisper-cpp", or future engine names
```

**Dependencies in `pyproject.toml`:**
- `faster-whisper` moves from hard dep to optional `[nvidia]`
- `pywhispercpp` added as optional `[universal]`
- Core package has zero inference engine deps — user installs what they need

**Consumer impact:** Only `__main__.py` changes (`Transcriber(...)` -> `create_transcriber(config)`). `hotkey.py`, `recorder.py`, UI — all unchanged. They call `.transcribe()` and don't know or care what engine runs.

**Model name mapping:** Users write `name = "large-v3-turbo"` in config. The factory maps to backend-specific identifiers (e.g., `"large-v3-turbo"` for faster-whisper, `"ggml-large-v3-turbo.bin"` for whisper.cpp). Non-Whisper backends define their own model naming.

### EXE Packaging: PyInstaller `--onedir`
- Not `--onefile` — CUDA DLLs (300-500MB) make single-file extraction too slow
- CTranslate2 loads CUDA dynamically — bundle DLLs in `_internal/cuda/`
- Startup: check system CUDA → fallback to bundled DLLs → fallback to CPU
- Expected size: ~500MB-1GB (PySide6 + CUDA DLLs + model)

### v0.2+ File Structure
```
keyvox/
├── __init__.py
├── __main__.py              # CLI entry + GUI launch (uses create_transcriber)
├── config.py                # existing (+ backend default)
├── recorder.py              # existing
├── hotkey.py                # existing (calls transcriber.transcribe — same interface)
├── setup_wizard.py          # existing (+ backend detection, recommend install command)
├── dictionary.py            # v0.2 — load/save/apply word corrections
├── history.py               # v0.2 — SQLite history store
├── backends/                # v0.3 — model-agnostic transcriber abstraction
│   ├── __init__.py          # create_transcriber() factory + auto-detect
│   ├── base.py              # TranscriberBackend Protocol (one method: transcribe)
│   ├── faster_whisper.py    # NVIDIA backend (current transcriber.py logic, moved here)
│   └── whisper_cpp.py       # Universal backend (whisper.cpp via pywhispercpp)
└── ui/                      # v0.2 — PySide6 UI
    ├── __init__.py
    ├── app.py               # QApplication + QSystemTrayIcon
    ├── main_window.py       # Main panel with tabs
    ├── history_panel.py     # Transcription history list
    ├── settings_panel.py    # Model/mic/hotkey config
    └── dictionary_editor.py # Word corrections table
```

**Migration from v0.1:** `transcriber.py` is replaced by `backends/faster_whisper.py` (same code, moved). `__main__.py` changes one line: `Transcriber(...)` -> `create_transcriber(config)`.
