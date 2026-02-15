"""Qwen3 ASR backend - supports NVIDIA/AMD/Intel/CPU."""
import os
import numpy as np
from typing import Optional


class QwenASRBackend:
    """Qwen3 ASR backend using transformers (PyTorch).

    Best for: All GPUs (NVIDIA/AMD/Intel) and CPU
    Pros: Excellent multilingual quality (52 languages), works on any GPU
    Cons: Slower than CTranslate2 on NVIDIA, larger memory footprint
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-ASR-1.7B",
        device: str = "cuda",
        compute_type: str = "bfloat16",
        model_cache: str = ""
    ):
        # Set cache paths BEFORE importing transformers/qwen-asr
        if model_cache:
            os.environ['HF_HOME'] = model_cache
            os.environ['HF_HUB_CACHE'] = os.path.join(model_cache, 'hub')
            os.environ['TRANSFORMERS_CACHE'] = os.path.join(model_cache, 'transformers')

        import torch
        from qwen_asr import Qwen3ASRModel

        # Map compute_type to torch dtype
        dtype_map = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }
        dtype = dtype_map.get(compute_type, torch.bfloat16)

        print(f"[INFO] Loading Qwen3 ASR model: {model_name} on {device}...")
        self.model = Qwen3ASRModel.from_pretrained(
            model_name,
            dtype=dtype,
            device_map=device if device != "cpu" else None,
            max_inference_batch_size=32,
            max_new_tokens=256,
        )
        print("[OK] Model loaded and ready")

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
