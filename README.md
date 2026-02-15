# KeyVox

Push-to-talk speech-to-text powered by Whisper on GPU.

Hold a hotkey, speak, release — your words are transcribed and pasted into the active window. Runs locally, no cloud, no latency.

## Prerequisites

- **Python 3.11+**
- **CUDA-compatible GPU** (NVIDIA) with 2GB+ VRAM
- **CUDA Toolkit** matching your GPU driver

> **Platform support:** KeyVox currently targets **Windows**. Linux and macOS support is planned — the core pipeline (sounddevice + faster-whisper + pynput) is cross-platform, but hotkey behavior and auto-paste may need adaptation.

## Installation

### 1. Install PyTorch with CUDA

Install PyTorch for your CUDA version. Example for CUDA 12.4:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

For other versions, see [pytorch.org/get-started](https://pytorch.org/get-started/locally/).

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
| `name` | `large-v3-turbo` | Whisper model (`tiny`, `small`, `medium`, `large-v3`, `large-v3-turbo`) |
| `device` | `cuda` | `cuda` or `cpu` |
| `compute_type` | `float16` | `float16` (GPU), `int8` (CPU), `float32` |

VRAM requirements: `tiny` ~1GB, `small` ~2GB, `medium` ~4GB, `large-v3-turbo` ~6GB.

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

## Troubleshooting

**No GPU detected** — Verify PyTorch sees your GPU: `python -c "import torch; print(torch.cuda.is_available())"`. Check CUDA Toolkit version matches PyTorch.

**Wrong microphone** — Run `keyvox --setup` to list devices, or set `input_device` in `config.toml` to the device index.

**Model download fails** — Check internet connection and disk space (models are 1-3GB). Verify the cache directory is writable.

**Transcription is slow** — Use a smaller model. Ensure `device = "cuda"` and `compute_type = "float16"`.

**"Already running"** — Check Task Manager for existing instances. Install `pywin32` for proper single-instance detection.

**Paste doesn't work** — Some apps block simulated keypresses. Set `auto_paste = false` and paste manually.

## License

MIT - see [LICENSE](LICENSE).
