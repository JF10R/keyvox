# Backend Guide

Keyvox supports multiple ASR backends through a model-agnostic architecture. Switch backends by editing `config.toml`.

## Available Backends

### faster-whisper (NVIDIA GPUs only)

**Best for:** NVIDIA GPUs with CUDA
**Pros:** Fastest inference on NVIDIA, excellent quality
**Cons:** NVIDIA-only, requires PyTorch + CUDA

```toml
[model]
backend = "faster-whisper"
name = "large-v3-turbo"
device = "cuda"
compute_type = "float16"
```

**Available models:**
- `tiny`, `base`, `small`, `medium` — smaller, faster
- `large-v3` — best quality, slower
- `large-v3-turbo` — recommended (best speed/quality tradeoff)

**Install:** `pip install faster-whisper`

---

### qwen-asr (Universal: NVIDIA/AMD/Intel/CPU)

**Best for:** All GPUs (NVIDIA/AMD/Intel) and CPU
**Pros:** Excellent multilingual quality (52 languages), works on any GPU, state-of-the-art code-switching
**Cons:** Slower than CTranslate2 on NVIDIA (~2-3x slower than `large-v3-turbo`, similar to `large-v3`), larger memory footprint

> **Performance note:** On NVIDIA GPUs, `Qwen3-ASR-1.7B` is roughly equivalent in speed to faster-whisper's `large-v3` (non-turbo), but slower than `large-v3-turbo`. The tradeoff is universal GPU support and superior multilingual/code-switching quality. If you don't need those features and have NVIDIA, stick with `large-v3-turbo`.

```toml
[model]
backend = "qwen-asr"
name = "Qwen/Qwen3-ASR-1.7B"
device = "cuda"
compute_type = "bfloat16"
```

**Available models:**
- `Qwen/Qwen3-ASR-0.6B` — smaller, faster (~3GB VRAM)
- `Qwen/Qwen3-ASR-1.7B` — recommended (better quality, ~6GB VRAM)

**Install:** `pip install qwen-asr`

---

### qwen-asr-vllm (Linux only - Experimental)

**Best for:** Linux users wanting fastest Qwen inference
**Pros:** 2-5x faster than transformers backend via vLLM optimization
**Cons:** **Linux only** (not supported on Windows), more complex dependencies

> **Platform compatibility:** vLLM requires Linux. Windows users should use `qwen-asr` (transformers) backend.

```toml
[model]
backend = "qwen-asr-vllm"
name = "Qwen/Qwen3-ASR-1.7B"
device = "cuda"
compute_type = "bfloat16"
```

**Install (Linux only):** `pip install qwen-asr[vllm]`

---

## Auto-Detection

Set `backend = "auto"` to automatically select the best backend:

```toml
[model]
backend = "auto"  # Detects NVIDIA → faster-whisper, else → qwen-asr
name = "large-v3-turbo"
device = "cuda"
compute_type = "float16"
```

When using auto-detection, the model name should match the expected backend. If NVIDIA is detected but you provide a Qwen model name, it may fail.

---

## Model Cache

All models download to `paths.model_cache` in `config.toml`:

```toml
[paths]
model_cache = "D:\\AI\\hf-cache"  # Windows
# model_cache = "/home/user/models"  # Linux/Mac
```

If empty, uses HuggingFace default cache (`~/.cache/huggingface`).

---

## Compute Types

### faster-whisper
- `float16` — recommended for GPU (fastest, good quality)
- `int8` — CPU mode (slower, lower VRAM)
- `float32` — highest precision (slower, more VRAM)

### qwen-asr
- `bfloat16` — recommended (best balance)
- `float16` — slightly faster, may have precision issues
- `float32` — highest precision (slower, more VRAM)

---

## Switching Backends

1. Edit `config.toml`
2. Change `backend`, `name`, `compute_type` to match
3. Run `keyvox` — it will download the new model on first run

**Example: Switch from faster-whisper to Qwen3 ASR**

Before:
```toml
[model]
backend = "faster-whisper"
name = "large-v3-turbo"
compute_type = "float16"
```

After:
```toml
[model]
backend = "qwen-asr"
name = "Qwen/Qwen3-ASR-1.7B"
compute_type = "bfloat16"
```

---

## Adding New Backends

See `CLAUDE.md` for architecture details. To add a new ASR engine:

1. Create `keyvox/backends/your_backend.py` with a class implementing:
   ```python
   def transcribe(self, audio_array: np.ndarray) -> str: ...
   ```
2. Add backend to `create_transcriber()` factory in `keyvox/backends/__init__.py`
3. Update `BACKENDS.md` with usage instructions

The Protocol is model-agnostic — any ASR engine (Conformer, Wav2Vec2, cloud APIs) can be added.
