# KeyVox

Push-to-talk speech-to-text powered by Whisper on GPU.

Hold a hotkey, speak, release — your words are transcribed and pasted into the active window. Runs locally, no cloud, no latency.

## How It Works

```
┌─────────┐    ┌───────────────┐    ┌─────────────────┐    ┌────────────────┐    ┌────────────┐
│ Hotkey   │───>│ Audio Capture │───>│ Speech-to-Text  │───>│ Post-process   │───>│ Paste into │
│ Listener │    │ (Microphone)  │    │ (Whisper model) │    │ (Dictionary)   │    │ Active App │
└─────────┘    └───────────────┘    └─────────────────┘    └────────────────┘    └────────────┘
  Hold key       Stream audio        GPU inference          Word corrections     Clipboard +
  to start       until release        on recorded chunk     and formatting       simulated Ctrl+V
```

**Core pipeline:**

1. **Hotkey listener** — global push-to-talk key, captured at OS level
2. **Audio capture** — microphone stream buffered while key is held
3. **Speech-to-text engine** — Whisper model runs GPU-accelerated inference on the audio
4. **Post-processing** — dictionary corrections, formatting (planned)
5. **Output** — text copied to clipboard and pasted into the active window

**Future components** (see [Roadmap](#roadmap)):

6. **Transcription history** — persistent, searchable log of all transcriptions
7. **System tray** — background operation with quick-access UI
8. **Settings UI** — graphical configuration, replacing the CLI wizard

This architecture is stack-agnostic — it describes *what* KeyVox does, not *how*. The current implementation uses Python + faster-whisper, but the pipeline would be the same in any language.

## Available Models

KeyVox uses [OpenAI Whisper](https://github.com/openai/whisper) models via the [faster-whisper](https://github.com/SYSTRAN/faster-whisper) engine (CTranslate2 backend) by default. A pluggable backend architecture (v0.3) will add [whisper.cpp](https://github.com/ggerganov/whisper.cpp) support for AMD/Intel GPUs and CPU-optimized inference. All models are downloaded automatically on first use.

| Model | Parameters | VRAM (float16) | Relative Speed | Quality | Best For |
|-------|-----------|----------------|----------------|---------|----------|
| `tiny` | 39M | ~1 GB | Fastest | Low | Testing, very low VRAM |
| `tiny.en` | 39M | ~1 GB | Fastest | Low | English-only, minimal resources |
| `base` | 74M | ~1 GB | Very fast | Fair | Low VRAM, acceptable accuracy |
| `base.en` | 74M | ~1 GB | Very fast | Fair | English-only, low VRAM |
| `small` | 244M | ~2 GB | Fast | Good | Budget GPUs (2-4 GB VRAM) |
| `small.en` | 244M | ~2 GB | Fast | Good | English-only, budget GPUs |
| `medium` | 769M | ~5 GB | Moderate | Great | Mid-range GPUs (6+ GB VRAM) |
| `medium.en` | 769M | ~5 GB | Moderate | Great | English-only, mid-range GPUs |
| `large-v2` | 1550M | ~10 GB | Slow | Excellent | High-end GPUs, max accuracy |
| `large-v3` | 1550M | ~10 GB | Slow | Excellent | Latest large model, multilingual |
| **`large-v3-turbo`** | 809M | ~6 GB | **Fast** | **Excellent** | **Recommended — best speed/quality tradeoff** |
| `distil-large-v3` | 756M | ~6 GB | Fast | Very good | Distilled, English-focused |
| `distil-medium.en` | 394M | ~3 GB | Fast | Good | Distilled, English-only |

**How to choose:**
- **6+ GB VRAM:** use `large-v3-turbo` (default) — near large-v3 quality at 2-3x the speed
- **4-5 GB VRAM:** use `medium`
- **2-3 GB VRAM:** use `small`
- **No GPU / CPU only:** use `tiny` or `base` with `device = "cpu"` and `compute_type = "int8"`

The `.en` variants are English-only and slightly more accurate for English than their multilingual counterparts. Use multilingual models if you speak in multiple languages.

## Prerequisites

- **Python 3.11+**
- **NVIDIA GPU** with 2+ GB VRAM (recommended, not required — CPU mode works but is slower). AMD/Intel GPU support planned for v0.3 via whisper.cpp backend

> **Note:** CUDA Toolkit installation is **not** required. PyTorch bundles its own CUDA runtime. You only need an up-to-date NVIDIA driver.

> **Platform:** KeyVox currently targets **Windows**. Linux and macOS support is planned (see [Roadmap](#roadmap)).

## Installation

### 1. Install PyTorch with CUDA

Install PyTorch for your CUDA version. Example for CUDA 12.4:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

For other versions, see [pytorch.org/get-started](https://pytorch.org/get-started/locally/).

**CPU only** (no NVIDIA GPU):

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### 2. Install KeyVox

```bash
git clone https://github.com/JF10R/keyvox.git
cd keyvox
pip install -e .
```

Optional single-instance protection (Windows):

```bash
pip install -e ".[singleton]"
```

### 3. Run setup wizard

```bash
keyvox --setup
```

Detects your GPU, recommends a model, lists microphones, and generates `config.toml`.

### 4. Start

```bash
keyvox
```

## Usage

1. Run `keyvox`
2. **Hold** the hotkey (default: Right Ctrl) and speak
3. **Release** — transcription is pasted into the active window
4. **ESC** to quit

## Configuration

KeyVox looks for `config.toml` in this order:

| Platform | Locations checked |
|----------|------------------|
| Windows  | `.\config.toml`, `%APPDATA%\keyvox\config.toml` |
| macOS    | `./config.toml`, `~/Library/Application Support/keyvox/config.toml` |
| Linux    | `./config.toml`, `$XDG_CONFIG_HOME/keyvox/config.toml` |

See `config.toml.example` for all options. Key sections:

### `[model]`

| Key | Default | Description |
|-----|---------|-------------|
| `name` | `large-v3-turbo` | Whisper model (see [Available Models](#available-models)) |
| `device` | `cuda` | `cuda` or `cpu` |
| `compute_type` | `float16` | `float16` (GPU), `int8` (CPU), `float32` |

### `[audio]`

| Key | Default | Description |
|-----|---------|-------------|
| `input_device` | `default` | Microphone: `"default"` or device index |
| `sample_rate` | `16000` | Sample rate in Hz |

### `[hotkey]`

| Key | Default | Description |
|-----|---------|-------------|
| `push_to_talk` | `ctrl_r` | `ctrl_r`, `ctrl_l`, `alt_r`, `alt_l`, `shift_r`, `shift_l` |

### `[paths]`

| Key | Default | Description |
|-----|---------|-------------|
| `model_cache` | `""` | Model download directory (empty = HuggingFace default `~/.cache/huggingface`) |

### `[output]`

| Key | Default | Description |
|-----|---------|-------------|
| `auto_paste` | `true` | Auto-paste via Ctrl+V after transcription |

## Autostart (Windows)

```powershell
schtasks /create /tn "KeyVox" /tr "pythonw -m keyvox" /sc onlogon /rl highest /f
```

Remove with:

```powershell
schtasks /delete /tn "KeyVox" /f
```

## Roadmap

### v0.2 — Desktop UI
- [ ] System tray icon (runs in background, click to open)
- [ ] Transcription history panel (timestamped, searchable, copyable)
- [ ] Dictionary / word corrections (auto-replace detected words with custom spellings)
- [ ] Settings panel (model, mic, hotkey — replaces CLI wizard)
- [ ] SQLite-backed history storage
- [ ] Export transcription history (TXT, CSV)

### v0.3 — Multi-Backend & Standalone EXE
- [ ] Model-agnostic backend abstraction (Protocol + factory pattern)
- [ ] whisper.cpp backend for AMD/Intel/CPU (Vulkan GPU, optimized CPU fallback)
- [ ] Auto-detect GPU vendor and select best backend
- [ ] PyInstaller packaging with bundled CUDA runtime
- [ ] Hardware detection and automatic model recommendation based on VRAM
- [ ] CPU-optimized mode (int8/q4 quantization, smaller models)
- [ ] Windows installer (MSI)
- [ ] Auto-update mechanism

### v0.4 — Quality & Benchmarking
- [ ] Built-in benchmark tool (compare models on your hardware: speed, VRAM, accuracy)
- [ ] Word Error Rate (WER) evaluation per model
- [ ] WER per language segment (quantify multilingual accuracy)
- [ ] Language detection switch accuracy (how well does auto-detect handle mid-speech switches)
- [ ] Punctuation and casing quality metrics
- [ ] Timestamp alignment quality evaluation
- [ ] Publish benchmark results in README or docs site

### v0.5 — Cross-platform
- [ ] Linux support (X11/Wayland hotkey, XDG paths)
- [ ] macOS support (Cmd key, Application Support paths)

### Future Ideas
- [ ] Streaming transcription (real-time text as you speak)
- [ ] Speaker diarization (identify who is speaking)
- [ ] Multi-language auto-detection with per-language dictionaries
- [ ] Whisper model hot-swap (switch models without restarting)
- [ ] Audio post-processing (noise reduction, gain normalization)
- [ ] Global search across transcription history
- [ ] Webhook / API output (send transcriptions to external services)
- [ ] Voice commands (trigger actions by speaking keywords)

## Troubleshooting

**No GPU detected** — Verify PyTorch sees your GPU: `python -c "import torch; print(torch.cuda.is_available())"`. Make sure your NVIDIA driver is up to date.

**Wrong microphone** — Run `keyvox --setup` to list devices, or set `input_device` in `config.toml` to the device index.

**Model download fails** — Check internet connection and disk space (models are 1-3 GB). Verify the cache directory is writable.

**Transcription is slow** — Use a smaller model (see [Available Models](#available-models)). Ensure `device = "cuda"` and `compute_type = "float16"`.

**"Already running"** — Check Task Manager for existing instances. Install `pywin32` for proper single-instance detection.

**Paste doesn't work** — Some apps block simulated keypresses. Set `auto_paste = false` and paste manually.

## License

MIT - see [LICENSE](LICENSE).
