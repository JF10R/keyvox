# Keyvox

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

**Current interfaces:**

7. **CLI runtime** — local push-to-talk flow with direct text insertion
8. **Desktop UI** — Tauri + Svelte app connected to `keyvox --server`

This architecture is stack-agnostic — it describes *what* Keyvox does, not *how*. The current implementation uses Python with a **pluggable backend architecture** supporting multiple ASR engines (faster-whisper, Qwen3 ASR, and extensible to others).

## ASR Backends

Keyvox supports multiple ASR backends through a model-agnostic architecture. Choose based on your hardware and needs:

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

> **Platform:** Keyvox currently targets **Windows**. Linux and macOS support is planned (see [Roadmap](#roadmap)).

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

> **Tip:** You can skip this step. `keyvox --setup` (step 3) detects your GPU via `nvidia-smi`
> and offers to install the correct PyTorch build automatically.

### 2. Install Keyvox

```bash
git clone https://github.com/JF10R/keyvox.git
cd keyvox
pip install -e .
```

**Choose your backend:**

```bash
# NVIDIA GPU (faster-whisper)
pip install -e ".[nvidia]"

# AMD/Intel/Universal (qwen-asr)
pip install qwen-asr

# Optional: single-instance protection (Windows)
pip install -e ".[singleton]"

# Optional: WebSocket server mode (frontend/backend decoupling)
pip install -e ".[server]"
```

### 3. Run setup wizard

```bash
keyvox --setup
```

Detects your GPU and CUDA version, recommends a model, lists microphones, and generates
`config.toml` in the platform config directory (`%APPDATA%\keyvox\` on Windows). If the
recommended model is already in your HuggingFace cache the download step is skipped automatically.

If PyTorch is not installed, the wizard detects your GPU via `nvidia-smi` and offers to install
the correct build (CUDA or CPU) before continuing.

### 4. Start

```bash
keyvox
```

## Usage

### CLI Mode (Default)

```bash
keyvox
```

1. **Hold** the hotkey (default: Right Ctrl) and speak
2. **Release** — transcription is pasted into the active window
3. **Double-tap** the hotkey to paste the last transcription again
4. **Ctrl+C** to quit (recommended)
5. **ESC** to quit only when supported and the Keyvox terminal is focused (`ESC` is disabled in Windows Terminal tabs)

### Headless Flag (Alias)

```bash
keyvox --headless
```

Runs the same CLI runtime as `keyvox`.

**Runtime config hot-reload:** Changes to `[dictionary]` and `[text_insertion]` in `config.toml` are applied automatically on the next hotkey release (no app restart required).

### Server Mode (WebSocket)

```bash
keyvox --server
# or custom port
keyvox --server --port 9999
```

Server mode exposes the transcription engine over `ws://localhost:<port>` and is intended for external UIs (for example, Tauri/electron/frontend shells).

**Behavior guarantees:**
- Binds to localhost only
- Allows a single client connection at a time
- Tries fallback ports when requested port is busy (`PORT..PORT+9`)
- Does **not** type/paste into the local active window (engine-only mode)
- Uses protocol version `1.0.0` with request/response correlation via `request_id`

**Command frame (client -> server):**

```json
{
  "type": "get_history",
  "request_id": "req-42",
  "limit": 100,
  "offset": 0,
  "search": ""
}
```

**Response envelope (server -> client):**

```json
{
  "type": "response",
  "protocol_version": "1.0.0",
  "timestamp": "2026-02-17T00:00:00+00:00",
  "request_id": "req-42",
  "response_type": "history",
  "ok": true,
  "result": { "entries": [], "total": 0, "limit": 100, "offset": 0, "search": "" }
}
```

Error responses keep the same envelope with `ok: false` and an `error` object:

```json
{
  "type": "response",
  "ok": false,
  "error": {
    "code": "invalid_payload",
    "message": "sample_rate must be a positive integer"
  }
}
```

**Primary commands:**

| Type | Purpose |
|------|---------|
| `ping`, `server_info`, `get_config`, `get_full_config` | Health and configuration reads |
| `get_capabilities`, `list_audio_devices`, `validate_model_config` | Capability discovery and pre-save validation |
| `download_model` | Background model download queueing and progress events |
| `get_storage_status`, `set_storage_root` | Storage root status, migration, and free-space guarded relocation |
| `set_config_section`, `set_hotkey`, `set_model`, `set_audio_device` | Configuration writes |
| `get_dictionary`, `set_dictionary`, `delete_dictionary` | Dictionary management |
| `get_history`, `delete_history_item`, `clear_history`, `export_history` | History operations |
| `shutdown` | Graceful backend stop |

**Async events (server -> client):**

| Type | Fields |
|------|--------|
| `state` | `state: idle|recording|processing` |
| `transcription` | `text`, `duration_ms`, `entry` |
| `history_appended` | `entry` |
| `model_download` | `status`, `backend`, `name`, `message` |
| `model_download_progress` | `download_id`, `status`, `progress_pct`, `bytes_total`, `bytes_completed`, `bytes_remaining` |
| `storage_migration` | `status`, `target_root`, `progress_pct`, `message`, optional byte counters |
| `storage_updated` | `storage_root`, `persisted` |
| `error` | `message` |
| `dictionary_updated` | `key`, `value` |
| `dictionary_deleted` | `key` |
| `shutting_down` | none |

### Desktop UI (Tauri + Svelte)

The new desktop UI lives in `apps/desktop/` and consumes the WebSocket protocol above.

```bash
cd apps/desktop
npm install
npm run doctor
npm run tauri dev
```

Desktop prerequisites on Windows: Rust toolchain, MSVC C++ tools, Windows SDK, WebView2.

See [`docs/desktop-ui.md`](docs/desktop-ui.md) for details.

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

Keyvox looks for `config.toml` in this order:

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

> **Desktop UI:** Backend/model/device/compute selectors with capabilities-driven validation are available in `apps/desktop/`.

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
| `storage_root` | `""` | Unified root for app-managed heavy data (`models`, `history`, `exports`, `runtime`) |
| `model_cache` | `""` | Model download directory (empty = HuggingFace default `~/.cache/huggingface`) |
| `history_db` | `""` | SQLite history DB path (empty = auto path next to `config.toml`) |

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

> **Desktop UI:** Dictionary entries can be managed visually in `apps/desktop/` Settings (add, edit, delete without touching `config.toml`).

### `[text_insertion]`

Smart capitalization and spacing based on cursor context:

| Key | Default | Description |
|-----|---------|-------------|
| `enabled` | `true` | Enable smart text insertion |
| `smart_capitalization` | `true` | Auto-capitalize after `. ! ?` and at document start |
| `smart_spacing` | `true` | Auto-add spaces based on context (no space before punctuation) |
| `normalize_urls` | `true` | Detect URL/domain-like text and normalize domains to ASCII lowercase (e.g., `Google.com` → `google.com`) |
| `www_mode` | `"explicit_only"` | Controls `www.` handling: `explicit_only` (keep only on explicit dictation), `always_strip`, or `never_strip` |
| `add_trailing_space` | `false` | Add space after sentence-ending punctuation |
| `context_max_chars` | `100` | Max characters to analyze from clipboard for context |
| `sentence_enders` | `".!?"` | Characters that end sentences (trigger capitalization) |
| `punctuation_starters` | `",.!?:;'\")}]"` | Don't add space before these characters |

**How it works:**

- **Capitalization:** Detects if cursor is at document start or after sentence-ending punctuation (`. ! ?`), then capitalizes first letter
- **Spacing:** Adds leading space when continuing mid-word, but not before punctuation or after opening brackets
- **URL/domain normalization:** Detects URL/domain-like tokens and normalizes domains to ASCII lowercase (`Google.com` → `google.com`)
- **WWW handling (`www_mode`):** In `explicit_only`, `www.` is kept only for explicit markers like `triple w google.com` (`www.Google.com` alone normalizes to `google.com`)
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

## Testing

- Full testing guide: [`docs/testing.md`](docs/testing.md)
- Current suite: **194 tests**
- Coverage command included below for local validation.

Run locally:

```bash
python -m pytest -q
python -m pytest --cov=keyvox --cov-report=term-missing -q
```

## Autostart (Windows)

```powershell
schtasks /create /tn "Keyvox" /tr "pythonw -m keyvox" /sc onlogon /rl highest /f
```

Remove with:

```powershell
schtasks /delete /tn "Keyvox" /f
```

## Roadmap

### What's been built

**Core pipeline:** push-to-talk recording → Whisper GPU transcription (async worker thread) → dictionary corrections → smart text insertion (context-aware capitalization, spacing, URL normalization) → clipboard paste. Hot-reload for dictionary and text insertion settings without restarting.

**Desktop UI (Tauri + Svelte):** settings panel, transcription history (timestamped, searchable, exportable TXT/CSV), dictionary CRUD, model download with byte-level progress, storage root migration with free-space precheck, dark/light theme, WCAG 2.1 AA accessibility.

**Multi-backend:** faster-whisper (NVIDIA), Qwen3 ASR (AMD/Intel/NVIDIA/CPU), GPU vendor auto-detection, VRAM-based model recommendation, capabilities-driven model/backend/device/compute selectors.

**Setup wizard:** GPU detection via `nvidia-smi`, guided PyTorch CUDA wheel install, guided faster-whisper install, microphone listing, config generation.

**Server mode:** WebSocket engine backend (`keyvox --server`) with request/response correlation, async state events, and full protocol for external UIs.

---

### P1 — Distribution
*Prerequisite for any non-developer user. Nothing else matters until someone can install Keyvox without knowing what pip is.*

- [ ] Write `keyvox.spec` for PyInstaller: bundle app + Python runtime into a standalone directory
- [ ] Identify and include CUDA + ctranslate2 DLLs in the PyInstaller bundle (required for GPU inference without a CUDA toolkit install)
- [ ] Write Inno Setup (or NSIS) installer script: wraps the bundle into a double-click `.exe`
- [ ] GitHub Actions release workflow: build the installer on version tag push, upload artifact to GitHub Releases
- [ ] Clean-VM install test: verify the installer works on a machine with no Python, no CUDA toolkit, no prior Keyvox
- [ ] Auto-update mechanism: check for new releases on launch, prompt user to download

### P2 — Tray & System Integration
*The tray icon exists (tooltip-only). These make Keyvox behave like a native Windows background utility instead of an app you leave open in a terminal.*

- [ ] Tray context menu: right-click → Show/Hide window, Quit (Rust/Tauri `Menu` + `on_menu_event`)
- [ ] Tray icon click: single-click toggles window visibility
- [ ] Engine state in tray: swap tray icon file (or tooltip text) to reflect idle / recording / processing
- [ ] Minimize to tray on window close: intercept the `CloseRequested` event; hide the window, keep backend running
- [ ] Open at login (Windows): write/delete `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry key
- [ ] Open at login toggle: checkbox in the desktop UI Settings panel, writes/deletes the registry key via a Tauri command

### P3 — Quality Baseline
*Professional-grade reliability. CI catches regressions before they ship; error messages give users a path forward instead of a traceback.*

- [ ] GitHub Actions: pytest on push (Windows runner, Python 3.11 + 3.12, runs on every PR)
- [ ] GitHub Actions: ruff linting (replaces flake8 + isort + pyupgrade, single fast pass)
- [ ] GitHub Actions: mypy type checking in strict mode on `keyvox/`
- [ ] Dependency lock file: add `uv.lock` for reproducible installs across environments
- [ ] Config schema version field: add `version = 1` to TOML; reject unknown versions with a clear, actionable message
- [ ] Config migration function: `migrate_config(old_dict) → new_dict`; auto-upgrades on load so old configs never silently break
- [ ] Actionable backend error: catch `ImportError` at backend load, print which package is missing and the exact install command
- [ ] Actionable CUDA OOM error: detect `RuntimeError: CUDA out of memory`, suggest a smaller model by name
- [ ] Actionable mic error: catch `sounddevice.PortAudioError`, list available devices and point to `--setup`
- [ ] Actionable model-load error: catch corrupt/missing model files, tell user to delete the cache entry and re-download

### P4 — Power User Polish
*Gaps that power users hit quickly. Each is a small, self-contained change.*

- [ ] Language config key: add `language` to `[model]` (default `null` = auto-detect); document supported values
- [ ] Pass `language` to faster-whisper and Qwen3 ASR backends
- [ ] Language selector in setup wizard (optional step, defaulting to auto-detect)
- [ ] Language selector in desktop UI Settings panel
- [ ] Minimum recording duration: add `min_duration_ms` to `[audio]` (default `300`); skip transcription and log a message on accidental short taps
- [ ] Hotkey conflict detection: after wizard/settings hotkey selection, attempt a test-register and warn if another process holds the key
- [ ] whisper.cpp backend via `pywhispercpp`: CPU-optimized inference, useful as a no-GPU fallback and future zero-Python packaging path

### P5 — Benchmarking & Evaluation
*Gives users data to choose the right model for their hardware. Gives the project credibility.*

- [ ] Built-in benchmark command (`keyvox --benchmark`): runs a fixed audio clip set through each available model, reports RTF (real-time factor), VRAM peak, and p50/p95 latency
- [ ] WER evaluation: compare transcription output against a reference transcript set
- [ ] WER per language: quantify multilingual accuracy across supported languages
- [ ] Language-switch detection accuracy: measure auto-detect reliability on mid-speech language switches
- [ ] Publish results: add benchmark table to README or dedicated docs page

### P6 — Cross-platform
- [ ] Linux: XDG config paths, X11/Wayland hotkey (`evdev` for Wayland), `xdotool`/`ydotool` text insertion
- [ ] macOS: Application Support paths, Cmd key support, Accessibility permission flow, `CGEventCreateKeyboardEvent` text insertion

### Future Ideas
- [ ] Hot words / wake words (always-on listening, activate on keyword)
- [ ] Streaming transcription (real-time partial text as you speak)
- [ ] Speaker diarization (identify who is speaking in multi-speaker audio)
- [ ] Per-language dictionaries (apply different corrections depending on detected language)
- [ ] Whisper model hot-swap (switch models without restarting)
- [ ] Audio post-processing (noise reduction, gain normalization before transcription)
- [ ] Global search across transcription history
- [ ] Webhook / API output (send transcriptions to external services)
- [ ] Voice commands (trigger configurable actions by speaking a keyword)

## Troubleshooting

**No GPU detected** — Verify PyTorch sees your GPU: `python -c "import torch; print(torch.cuda.is_available())"`. Make sure your NVIDIA driver is up to date.

**Wrong microphone** — Run `keyvox --setup` to list devices, or set `input_device` in `config.toml` to the device index.

**Model download fails** — Check internet connection and disk space (models are 1-3 GB). Verify the cache directory is writable.

**Transcription is slow** — Use a smaller model (see [Available Models](#available-models)). Ensure `device = "cuda"` and `compute_type = "float16"`.

**"Already running"** — Check Task Manager for existing instances. Install `pywin32` for proper single-instance detection.

**Paste doesn't work** — Some apps block simulated keypresses. Set `auto_paste = false` and paste manually.

## License

MIT - see [LICENSE](LICENSE).
