"""Non-blocking transcription worker for Qt thread pool.

Moves GPU-intensive transcription off the main thread to keep UI responsive.
"""

from PySide6.QtCore import QRunnable, QObject, Signal


class TranscriptionWorkerSignals(QObject):
    """Signals for TranscriptionWorker.

    QRunnable cannot have signals directly, so we use a separate QObject.
    """
    completed = Signal(str)  # Emits transcribed text
    error = Signal(str)      # Emits error message


class TranscriptionWorker(QRunnable):
    """Non-blocking transcription worker for QThreadPool.

    Runs transcription in background thread, emitting signals on completion/error.
    Keeps UI responsive during 1-3 second GPU inference.
    """

    def __init__(self, audio, transcriber, dictionary, text_inserter):
        """Initialize transcription worker.

        Args:
            audio: np.ndarray audio samples to transcribe
            transcriber: Backend transcriber instance
            dictionary: Dictionary instance for word corrections
            text_inserter: TextInserter instance for post-processing (or None)
        """
        super().__init__()
        self.audio = audio
        self.transcriber = transcriber
        self.dictionary = dictionary
        self.text_inserter = text_inserter
        self.signals = TranscriptionWorkerSignals()

    def run(self):
        """Execute transcription in worker thread.

        Called by QThreadPool. Emits completed or error signal when done.
        """
        try:
            # GPU transcription (blocking in worker thread, non-blocking for UI)
            text = self.transcriber.transcribe(self.audio)

            # Post-processing
            if text:
                text = self.dictionary.apply(text)
                if self.text_inserter:
                    text = self.text_inserter.process(text)

            self.signals.completed.emit(text or "")
        except Exception as e:
            self.signals.error.emit(str(e))
