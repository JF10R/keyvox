# Keyvox — Project Conventions

## What is this?

Local push-to-talk speech-to-text: hold hotkey, speak, release, text appears in active window. GPU-accelerated via faster-whisper (CTranslate2), qwen-asr, or qwen-asr-vllm backends. Python package, not an EXE (CUDA version flexibility).

## Architecture

```
keyvox/
  __main__.py         # CLI entry point (argparse), single-instance check
  config.py           # TOML config loading/saving, platform-aware paths
  config_reload.py    # Hot config reload via file watching
  recorder.py         # AudioRecorder — sounddevice InputStream wrapper
  text_insertion.py   # Text insertion abstraction (clipboard + paste)
  hotkey.py           # HotkeyManager — pynput listener, paste via Ctrl+V
  setup_wizard.py     # Interactive --setup: GPU detect, mic list, model recommend
  dictionary.py       # Word corrections post-processing
  backends/           # Model-agnostic transcriber backends
    base.py           # TranscriberBackend Protocol
    __init__.py       # create_transcriber() factory + auto-detect
    faster_whisper.py # NVIDIA backend (CTranslate2)
    qwen_asr.py       # Qwen2-Audio ASR backend (cross-platform)
    qwen_asr_vllm.py  # Qwen2-Audio + vLLM (Linux-only, faster)
  ui/                 # PySide6 GUI
    window_chrome.py  # Custom window chrome
    styles/           # Design system (tokens + utils)
```

## Key decisions

- **faster-whisper** as default backend — avoids torchcodec/pyannote errors; other backends pluggable via Protocol
- **Default model:** `large-v3-turbo` (distilled, fast, near large-v3 quality)
- **torch not in dependencies** — users install the right version for their CUDA
- **No emojis in output** — plain markers: `[INFO]`, `[OK]`, `[REC]`, `[ERR]`, `[WARN]`
- **Config lookup order:** CWD → platform config dir (APPDATA / XDG / Library)
- **Single instance:** win32event.CreateMutex with ImportError fallback
- **Hot config reload** — `config_reload.py` watches config.toml for changes
- **Text insertion abstraction** — `text_insertion.py` separates clipboard/paste from hotkey logic

## Platform support

- **Windows:** primary target, fully functional
- **Linux/macOS:** planned — core pipeline is cross-platform, but hotkey/paste behavior needs testing and adaptation

## Stack

| Dependency | Purpose |
|-----------|---------|
| `faster-whisper` | Whisper inference — NVIDIA/CUDA (CTranslate2 backend) |
| `qwen-asr` (dynamic) | Qwen2-Audio ASR — cross-platform (CPU/GPU) |
| `qwen-asr[vllm]` (dynamic) | Qwen2-Audio + vLLM — Linux-only, optimized inference |
| `sounddevice` | Mic capture (PortAudio) |
| `pynput` | Global hotkey + simulated paste |
| `pyperclip` | Clipboard |
| `numpy` | Audio array handling |
| `pywin32` (optional) | Single-instance mutex on Windows |
| `PySide6` (optional) | GUI framework for tray + settings |

## Development

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -e ".[singleton]"
keyvox --setup
keyvox
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=keyvox --cov-report=html --cov-report=term

# Coverage artifacts (add to .gitignore):
# .coverage, coverage.xml, htmlcov/, .tracecov/
```

- 184 tests, 100% coverage
- Test files: `tests/test_*.py` pattern
- No pytest.ini — uses pytest defaults

## Conventions

- Python 3.11+ (uses `tomllib` from stdlib)
- Minimal dependencies — no unnecessary abstractions
- Config via TOML, not CLI flags (CLI only has `--setup`)
- Hardcoded user paths are a bug — always use empty defaults or platform detection

## .gitignore Notes

Coverage artifacts should be added to .gitignore:
```
.coverage
coverage.xml
htmlcov/
.tracecov/
.pytest_cache/
```

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

**Backend implementations (as of v0.3):**
- `faster_whisper.py` — NVIDIA GPUs via CTranslate2 (Whisper models)
- `qwen_asr.py` — Qwen2-Audio ASR (cross-platform, CPU/GPU)
- `qwen_asr_vllm.py` — Qwen2-Audio + vLLM (Linux-only, optimized inference)
- Future: any ASR engine that implements `transcribe(np.ndarray) -> str`

**Config:**
```toml
[model]
backend = "auto"  # "auto", "faster-whisper", "qwen-asr", "qwen-asr-vllm"
```

**Dependencies in `pyproject.toml`:**
- `faster-whisper` is currently a hard dependency (TODO: make optional)
- Qwen backends imported dynamically but not in optional deps yet
- Future: move all backends to optional dependencies based on use case

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
├── config.py                # TOML config loading/saving
├── config_reload.py         # v0.2 — hot config reload via file watching
├── recorder.py              # AudioRecorder wrapper
├── text_insertion.py        # v0.2 — text insertion abstraction
├── hotkey.py                # HotkeyManager (calls transcriber.transcribe)
├── setup_wizard.py          # Interactive setup (+ backend detection)
├── dictionary.py            # v0.2 — load/save/apply word corrections
├── backends/                # v0.3 — model-agnostic transcriber abstraction
│   ├── __init__.py          # create_transcriber() factory + auto-detect
│   ├── base.py              # TranscriberBackend Protocol (one method: transcribe)
│   ├── faster_whisper.py    # NVIDIA backend (CTranslate2)
│   ├── qwen_asr.py          # Qwen2-Audio backend (cross-platform)
│   └── qwen_asr_vllm.py     # Qwen2-Audio + vLLM (Linux-only)
└── ui/                      # v0.2 — PySide6 UI
    ├── __init__.py
    ├── window_chrome.py     # Custom window chrome
    └── styles/              # Design system
        ├── tokens.py        # Design tokens
        └── utils.py         # Style utilities
```

**Migration from v0.1:** `transcriber.py` is replaced by `backends/faster_whisper.py`. `__main__.py` changes one line: `Transcriber(...)` -> `create_transcriber(config)`.
