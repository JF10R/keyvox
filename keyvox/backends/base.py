"""Base protocol for transcriber backends."""
from typing import Protocol
import numpy as np


class TranscriberBackend(Protocol):
    """Protocol for ASR model backends.

    Any ASR engine (Whisper, Qwen3, Wav2Vec2, cloud APIs, etc.) can implement
    this interface. The only requirement is a transcribe method that takes audio
    and returns text.
    """

    def transcribe(self, audio_array: np.ndarray) -> str:
        """Transcribe audio to text.

        Args:
            audio_array: Audio samples as numpy array (float32, 16kHz assumed)

        Returns:
            Transcribed text string
        """
        ...
