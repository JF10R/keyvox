# KeyVox — Project Conventions

## What is this?

Local push-to-talk speech-to-text: hold hotkey, speak, release, text appears in active window. GPU-accelerated via faster-whisper (CTranslate2). Python package, not an EXE (CUDA version flexibility).

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

- **faster-whisper** over whisperx — avoids torchcodec/pyannote errors
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
| `faster-whisper` | Whisper inference (CTranslate2 backend) |
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
