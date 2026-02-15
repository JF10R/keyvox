"""Qwen3 ASR vLLM backend - optimized inference for all GPUs (Linux only)."""
import os
import sys
import numpy as np
from typing import Optional


class QwenASRVLLMBackend:
    """Qwen3 ASR vLLM-optimized backend (faster than transformers).

    Best for: All GPUs (NVIDIA/AMD/Intel) and CPU with faster inference
    Pros: 2-5x faster than transformers backend, same quality, batch processing
    Cons: More complex dependency (vLLM), version-sensitive
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-ASR-1.7B",
        device: str = "cuda",
        compute_type: str = "bfloat16",
        model_cache: str = ""
    ):
        # Check platform - vLLM only supports Linux
        if sys.platform == "win32":
            raise RuntimeError(
                "vLLM backend is not supported on Windows. "
                "Use 'qwen-asr' (transformers) backend instead, or run KeyVox on Linux/WSL2.\n"
                "To switch: set backend = 'qwen-asr' in config.toml"
            )

        # Set cache paths BEFORE importing transformers/qwen-asr
        if model_cache:
            os.environ['HF_HOME'] = model_cache
            os.environ['HF_HUB_CACHE'] = os.path.join(model_cache, 'hub')

        from qwen_asr import Qwen3ASRModel

        print(f"[INFO] Loading Qwen3 ASR model (vLLM): {model_name} on {device}...")

        # vLLM uses .LLM() instead of .from_pretrained()
        self.model = Qwen3ASRModel.LLM(
            model=model_name,
            gpu_memory_utilization=0.7,  # Leave 30% for overhead
            max_inference_batch_size=32,
            max_new_tokens=256,
        )
        print("[OK] Model loaded and ready (vLLM accelerated)")

    def transcribe(self, audio_array: Optional[np.ndarray]) -> str:
        """Transcribe audio to text."""
        if audio_array is None or len(audio_array) == 0:
            return ""

        try:
            # Qwen3 ASR expects (audio_array, sample_rate) tuple
            results = self.model.transcribe(
                audio=(audio_array, 16000),
                language=None,  # Auto-detect
            )

            text = results[0].text.strip() if results else ""

            if text:
                print(f'[TEXT] "{text}"')
            else:
                print("[WARN] No speech detected")

            return text
        except Exception as e:
            print(f"[ERR] Transcription failed: {e}")
            return ""
