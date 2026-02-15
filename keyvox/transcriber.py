"""Transcription module using Faster Whisper."""
import os
import numpy as np
from faster_whisper import WhisperModel
from typing import Optional


class Transcriber:
    """Handles speech-to-text transcription."""

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: str = "float16",
        model_cache: str = ""
    ):
        # Set cache paths before importing
        if model_cache:
            os.environ['HF_HOME'] = model_cache
            os.environ['HF_HUB_CACHE'] = os.path.join(model_cache, 'hub')

        print(f"[INFO] Loading Whisper model: {model_name} on {device}...")
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
