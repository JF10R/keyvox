"""Audio recording module."""
import sounddevice as sd
import numpy as np
import queue
from typing import Optional


class AudioRecorder:
    """Manages audio recording from microphone."""

    def __init__(self, sample_rate: int = 16000, input_device: str = "default"):
        self.sample_rate = sample_rate
        self.input_device = None if input_device == "default" else input_device
        self.is_recording = False
        self.audio_queue: Optional[queue.Queue] = None
        self.stream: Optional[sd.InputStream] = None

    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream."""
        if self.is_recording and self.audio_queue is not None:
            self.audio_queue.put(indata.copy())

    def start(self) -> None:
        """Start recording audio."""
        if self.is_recording:
            return  # Ignore key repeat

        self.is_recording = True
        self.audio_queue = queue.Queue()
        print("[REC] Recording...")

        self.stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype='float32',
            callback=self._audio_callback,
            device=self.input_device
        )
        self.stream.start()

    def stop(self) -> Optional[np.ndarray]:
        """Stop recording and return audio data."""
        if not self.is_recording:
            return None

        self.is_recording = False

        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        print("[INFO] Stopped, transcribing...")

        # Collect audio data from queue
        audio_data = []
        while self.audio_queue and not self.audio_queue.empty():
            audio_data.append(self.audio_queue.get())

        if not audio_data:
            print("[WARN] No audio recorded")
            return None

        # Concatenate and return
        audio = np.concatenate(audio_data, axis=0).squeeze()
        return audio
