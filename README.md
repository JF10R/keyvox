# KeyVox

Push-to-talk speech-to-text powered by Whisper on GPU.

Hold a hotkey, speak, release — your words are transcribed and pasted into the active window. Runs locally, no cloud, no latency.

## How It Works

```
┌─────────┐    ┌───────────────┐    ┌─────────────────┐    ┌────────────────┐    ┌─────────────────┐    ┌────────────┐
│ Hotkey   │───>│ Audio Capture │───>│ Speech-to-Text  │───>│ Dictionary     │───>│ Smart Text      │───>│ Paste into │
│ Listener │    │ (Microphone)  │    │ (Whisper model) │    │ Corrections    │    │ Insertion       │    │ Active App │
└─────────┘    └───────────────┘    └─────────────────┘    └────────────────┘    └─────────────────┘    └────────────┘
  Hold key       Stream audio        GPU inference          Word corrections     Context-aware       Clipboard +
  to start       until release        on recorded chunk     (GitHub, WhatsApp)   capitalization      simulated Ctrl+V
                                                                                  and spacing
```

**Core pipeline:**

1. **Hotkey listener** — global push-to-talk key, captured at OS level
2. **Audio capture** — microphone stream buffered while key is held
3. **Speech-to-text engine** — Whisper model runs GPU-accelerated inference on the audio
4. **Dictionary corrections** — case-insensitive word replacements (e.g., "github" → "GitHub")
5. **Smart text insertion** — context-aware capitalization, spacing, and URL/domain normalization
6. **Output** — text copied to clipboard and pasted into the active window

**Future components** (see [Roadmap](#roadmap)):

6. **Transcription history** — persistent, searchable log of all transcriptions
7. **System tray** — background operation with quick-access UI
8. **Settings UI** — graphical configuration, replacing the CLI wizard

This architecture is stack-agnostic — it describes *what* KeyVox does, not *how*. The current implementation uses Python with a **pluggable backend architecture** supporting multiple ASR engines (faster-whisper, Qwen3 ASR, and extensible to others).

## ASR Backends

KeyVox supports multiple ASR backends through a model-agnostic architecture. Choose based on your hardware and needs:

### faster-whisper (NVIDIA GPUs)

**Best for:** NVIDIA GPUs with CUDA
**Pros:** Fastest inference on NVIDIA, excellent quality, low VRAM usage
**Cons:** NVIDIA-only

### Qwen3 ASR (Universal)

**Best for:** AMD/Intel GPUs, multilingual workflows, code-switching
**Pros:** Works on any GPU (NVIDIA/AMD/Intel) and CPU, state-of-the-art multilingual quality (52 languages), handles mid-speech language switches
**Cons:** Slower than faster-whisper on NVIDIA, larger memory footprint

See [BACKENDS.md](BACKENDS.md) for switching instructions and detailed comparison.

---

## Available Models

All models are downloaded automatically on first use to your configured cache directory.

### faster-whisper Models

| Model | Parameters | VRAM | Speed | Quality | Best For |
|-------|-----------|------|-------|---------|----------|
| `tiny` | 39M | ~1 GB | Fastest | Low | Testing, very low VRAM |
| `base` | 74M | ~1 GB | Very fast | Fair | Low VRAM, acceptable accuracy |
| `small` | 244M | ~2 GB | Fast | Good | Budget GPUs (2-4 GB VRAM) |
| `medium` | 769M | ~5 GB | Moderate | Great | Mid-range GPUs (6+ GB VRAM) |
| `large-v3` | 1550M | ~10 GB | Slow | Excellent | High-end GPUs, max accuracy |
| **`large-v3-turbo`** | **809M** | **~6 GB** | **Fast** | **Excellent** | **Recommended for NVIDIA** |

The `.en` variants (`tiny.en`, `base.en`, etc.) are English-only and slightly more accurate for English.

### Qwen3 ASR Models

| Model | Parameters | VRAM | Speed | Quality | Best For |
|-------|-----------|------|-------|---------|----------|
| `Qwen/Qwen3-ASR-0.6B` | 600M | ~3 GB | Fast | Very good | Budget GPUs, good multilingual |
| **`Qwen/Qwen3-ASR-1.7B`** | **1.7B** | **~6 GB** | **Moderate** | **Excellent** | **Recommended for multilingual/code-switching** |

---

## Model Selection Guide

### By Hardware

| Your GPU | Recommended Backend | Recommended Model | Why |
|----------|-------------------|------------------|-----|
| **NVIDIA 6+ GB** | `faster-whisper` | `large-v3-turbo` | Fastest inference, excellent quality |
| **NVIDIA 4-5 GB** | `faster-whisper` | `medium` | Good balance for mid-range GPUs |
| **NVIDIA 2-3 GB** | `faster-whisper` | `small` | Fits in VRAM, acceptable quality |
| **AMD/Intel GPU** | `qwen-asr` | `Qwen/Qwen3-ASR-1.7B` | Only backend supporting non-NVIDIA |
| **CPU only** | `faster-whisper` | `tiny` or `base` (int8) | Faster than Qwen on CPU |

### By Use Case

| Use Case | Recommended Backend | Recommended Model | Why |
|----------|-------------------|------------------|-----|
| **English only** | `faster-whisper` | `large-v3-turbo` | Fastest, excellent English quality |
| **Single foreign language** | `faster-whisper` | `large-v3-turbo` | Good multilingual support |
| **Multi-language code-switching** | `qwen-asr` | `Qwen/Qwen3-ASR-1.7B` | State-of-the-art at handling mid-speech language switches |
| **52 languages/22 Chinese dialects** | `qwen-asr` | `Qwen/Qwen3-ASR-1.7B` | Widest language coverage |
| **Budget GPU (2-4 GB)** | `faster-whisper` | `small` or `medium` | Best quality for limited VRAM |
| **Maximum speed** | `faster-whisper` | `base` or `small` | Lowest latency |
| **Maximum accuracy** | `faster-whisper` | `large-v3` | Best WER, requires 10+ GB VRAM |

## Prerequisites

- **Python 3.11+**
- **GPU** with 2+ GB VRAM (recommended, not required)
  - **NVIDIA:** Use `faster-whisper` backend (fastest)
  - **AMD/Intel:** Use `qwen-asr` backend (works on any GPU)
  - **CPU only:** Both backends work, `faster-whisper` is faster

> **Note:** CUDA Toolkit installation is **not** required. PyTorch bundles its own CUDA runtime. You only need an up-to-date GPU driver.

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

**Choose your backend:**

```bash
# NVIDIA GPU (faster-whisper) - default, already installed
pip install faster-whisper

# AMD/Intel/Universal (qwen-asr)
pip install qwen-asr

# Optional: single-instance protection (Windows)
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
4. **Double-tap** the hotkey to paste the last transcription again
5. **ESC** to quit

**Runtime config hot-reload:** Changes to `[dictionary]` and `[text_insertion]` in `config.toml` are applied automatically on the next hotkey release (no app restart required).

### Switching Models

Edit `config.toml` to change backend or model:

```toml
# Example: Switch from faster-whisper to Qwen3 ASR
[model]
backend = "qwen-asr"                    # was: "faster-whisper"
name = "Qwen/Qwen3-ASR-1.7B"           # was: "large-v3-turbo"
compute_type = "bfloat16"              # was: "float16"
```

Restart `keyvox` — the new model downloads automatically on first run.

See [BACKENDS.md](BACKENDS.md) for detailed backend comparison and recommendations.

## Configuration

KeyVox looks for `config.toml` in this order:

| Platform | Locations checked |
|----------|------------------|
| Windows  | `.\config.toml`, `%APPDATA%\keyvox\config.toml` |
| macOS    | `./config.toml`, `~/Library/Application Support/keyvox/config.toml` |
| Linux    | `./config.toml`, `$XDG_CONFIG_HOME/keyvox/config.toml` |

See `config.toml.example` for all options. Key sections:

> **Hot-reload scope:** `[dictionary]` and `[text_insertion]` are hot-reloaded at runtime.  
> **Restart required:** `[model]`, `[audio]`, and backend/device changes.

### `[model]`

| Key | Default | Description |
|-----|---------|-------------|
| `backend` | `auto` | `auto` (detect best), `faster-whisper`, `qwen-asr` |
| `name` | `large-v3-turbo` | Model name (see [Available Models](#available-models)) |
| `device` | `cuda` | `cuda` or `cpu` |
| `compute_type` | `float16` | faster-whisper: `float16`, `int8`, `float32`; qwen-asr: `bfloat16`, `float16`, `float32` |

See [BACKENDS.md](BACKENDS.md) for backend-specific configuration and switching instructions.

> **Note:** Backend and model selection currently requires manual config editing. A future UI update (v0.3) will add a dropdown selector in the settings panel for easy switching.

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
| `paste_method` | `type` | Paste method: `type` (no clipboard), `clipboard` (Ctrl+V), `clipboard-restore` (paste + restore) |
| `double_tap_to_clipboard` | `true` | Enable double-tap to paste last transcription |
| `double_tap_timeout` | `0.5` | Max seconds between taps to trigger double-tap (0.3-1.0 recommended) |

### `[dictionary]`

Custom word corrections applied to transcriptions (case-insensitive matching):

```toml
[dictionary]
github = "GitHub"
whatsapp = "WhatsApp"
openai = "OpenAI"
```

Words are matched with word boundaries — "github" matches but "githubbing" doesn't.

### `[text_insertion]`

Smart capitalization and spacing based on cursor context:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable smart text insertion |
| `smart_capitalization` | `true` | Auto-capitalize after `. ! ?` and at document start |
| `smart_spacing` | `true` | Auto-add spaces based on context (no space before punctuation) |
| `normalize_urls` | `true` | Detect URL/domain-like text and normalize domains to ASCII lowercase (e.g., `Google.com` → `google.com`) |
| `add_trailing_space` | `false` | Add space after sentence-ending punctuation |
| `context_max_chars` | `100` | Max characters to analyze from clipboard for context |
| `sentence_enders` | `".!?"` | Characters that end sentences (trigger capitalization) |
| `punctuation_starters` | `",.!?:;'\")}]"` | Don't add space before these characters |

**How it works:**

- **Capitalization:** Detects if cursor is at document start or after sentence-ending punctuation (`. ! ?`), then capitalizes first letter
- **Spacing:** Adds leading space when continuing mid-word, but not before punctuation or after opening brackets
- **URL/domain normalization:** Detects URL/domain-like tokens and normalizes domains to ASCII lowercase (`Google.com` → `google.com`)
- **Context detection:** Reads clipboard content (Windows) to determine cursor position context
- **Dictionary integration:** Respects dictionary casing — won't capitalize "github" at sentence start if dictionary has "GitHub"

**Example:**

```
Notepad content: "Hello world."
You say: "how are you"
Result: "Hello world. How are you"  (space + capitalize)

Notepad content: "Hello"
You say: "comma world"
Result: "Hello, world"  (no space before comma)
```

**Opt-out:** Set `enabled = false` to disable. Feature works on Windows; gracefully degrades on Linux/macOS (no context detection yet).

## Autostart (Windows)

```powershell
schtasks /create /tn "KeyVox" /tr "pythonw -m keyvox" /sc onlogon /rl highest /f
```

Remove with:

```powershell
schtasks /delete /tn "KeyVox" /f
```

## Roadmap

### v0.2 — Desktop UI & UX Improvements
- [x] **Clipboard management modes:**
  - [x] **Type mode (no clipboard pollution, default)**
  - [x] **Clipboard mode (traditional Ctrl+V paste)**
  - [x] **Clipboard-restore mode (paste then restore previous clipboard)**
- [x] **Double-tap to paste (tap hotkey twice to instantly paste last transcription)** ✅ Tested
- [x] **Dictionary corrections (case-insensitive word replacements)** ✅ Tested
- [x] **Smart text insertion (context-aware capitalization and spacing)** ✅ Tested
- [x] **URL/domain normalization (auto-detect domains and normalize casing, e.g., `Google.com` → `google.com`)** ✅ Tested
- [x] **Runtime hot-reload for `[dictionary]` and `[text_insertion]`** ✅ Tested
- [ ] Visual recording/processing indicator
  - [ ] Show feedback in active input when holding hotkey
  - [ ] Show "processing..." indicator after release, before text appears
- [ ] System tray icon (runs in background, click to open)
- [ ] Transcription history panel (timestamped, searchable, copyable)
- [ ] SQLite-backed history storage
- [ ] Settings panel (model, mic, hotkey — replaces CLI wizard)
- [ ] Export transcription history (TXT, CSV)

### v0.3 — Multi-Backend & Standalone EXE
- [x] **Model-agnostic backend abstraction (Protocol + factory pattern)**
- [x] **Qwen3 ASR backend for AMD/Intel/NVIDIA/CPU (universal support)**
- [x] **Auto-detect GPU vendor and select best backend**
- [ ] UI dropdown for model/backend selection (replaces manual config editing)
- [ ] whisper.cpp backend (additional option for CPU-optimized inference)
- [ ] PyInstaller packaging with bundled CUDA runtime
- [ ] Hardware detection and automatic model recommendation based on VRAM
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
- [ ] Hot words / wake words (always-on listening, activate on keyword)
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
