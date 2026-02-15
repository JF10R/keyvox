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

        print(f"[INFO] Loading Faster Whisper model: {model_name} on {device}...")
        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)
        print("[OK] Model loaded and ready")

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
