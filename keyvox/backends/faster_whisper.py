"""Faster Whisper backend (CTranslate2) - NVIDIA GPUs only."""
import os
import numpy as np
from typing import Optional


class FasterWhisperBackend:
    """NVIDIA GPU backend using faster-whisper (CTranslate2).

    Best for: NVIDIA GPUs with CUDA support
    Pros: Fastest inference on NVIDIA, excellent quality
    Cons: NVIDIA-only, requires PyTorch + CUDA
    """

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: str = "float16",
        model_cache: str = ""
    ):
        # Set cache paths BEFORE importing faster_whisper
        if model_cache:
            os.environ['HF_HOME'] = model_cache
            os.environ['HF_HUB_CACHE'] = os.path.join(model_cache, 'hub')

        from faster_whisper import WhisperModel

        self.model_name = model_name
        print(f"[INFO] Loading Faster Whisper model: {model_name} on {device}...")
        try:
            self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
            print("[OK] Model loaded and ready")
        except Exception as e:
            msg = str(e).lower()
            if any(kw in msg for kw in ("corrupt", "model", "load", "download")):
                print(f"[ERR] Failed to load model '{model_name}': {e}")
                print("      The model cache may be corrupt. Delete and re-download:")
                print("      Delete the model from your cache directory, then restart keyvox.")
            raise

    def transcribe(self, audio_array: Optional[np.ndarray]) -> str:
        """Transcribe audio to text."""
        if audio_array is None or len(audio_array) == 0:
            return ""

        try:
            segments, _ = self.model.transcribe(
                audio_array,
                language=None,  # Auto-detect
                vad_filter=False
            )

            text = " ".join(seg.text.strip() for seg in segments).strip()

            if text:
                print(f'[TEXT] "{text}"')
            else:
                print("[WARN] No speech detected")

            return text
        except Exception as e:
            print(f"[ERR] Transcription failed: {e}")
            return ""
