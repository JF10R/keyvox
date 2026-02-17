"""Transcription worker pipeline: moves GPU inference off the pynput listener thread."""
import queue
import threading
from typing import Any, Callable, Optional


class TranscriptionPipeline:
    """Worker thread that owns the inference pipeline.

    The listener thread calls enqueue(audio) — returns in <1ms.
    The worker thread runs transcription, dictionary, text insertion, and output_fn.
    """

    def __init__(
        self,
        transcriber,
        dictionary,
        text_inserter,
        output_fn: Callable[[str], None],
    ):
        """
        Args:
            transcriber: Backend with .transcribe(audio) -> str
            dictionary: DictionaryManager with .apply(text) -> str
            text_inserter: Optional TextInserter with .process(text) -> str, or None
            output_fn: Called with final text on worker thread (paste, no-op, etc.)
        """
        self._transcriber = transcriber
        self._dictionary = dictionary
        self._text_inserter = text_inserter
        self._output_fn = output_fn
        self._queue: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()  # guards _last_text, _dictionary, _text_inserter
        self._last_text: str = ""

        # Callbacks wired by caller (all called from worker thread)
        self.transcription_started: Optional[Callable[[], None]] = None
        self.transcription_completed: Optional[Callable[[str], None]] = None
        self.error_occurred: Optional[Callable[[str], None]] = None

    def start(self) -> None:
        """Start the worker thread."""
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="keyvox-pipeline"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal stop and join the worker thread (timeout=5s)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def enqueue(self, audio: Any) -> None:
        """Submit audio for transcription. Returns immediately (<1ms)."""
        self._queue.put(audio)

    def replay_last(self) -> None:
        """Double-tap: re-run output_fn on last transcribed text."""
        with self._lock:
            last = self._last_text
        if last:
            self._output_fn(last)
            print("[OK] Double-tap detected - Last transcription pasted")
        else:
            print("[INFO] Double-tap detected but no previous transcription available")

    def reload_config(self, config: dict) -> None:
        """Hot-reload dictionary and text_inserter from updated config."""
        new_dict = self._dictionary.__class__.load_from_config(config)
        new_inserter = None
        if self._text_inserter is not None:
            new_inserter = self._text_inserter.__class__(
                config=config.get("text_insertion", {}),
                dictionary_corrections=new_dict.corrections,
            )
        with self._lock:
            self._dictionary = new_dict
            self._text_inserter = new_inserter
        print("[INFO] Hot-reloaded config: dictionary/text_insertion")

    def _worker(self) -> None:
        """Worker loop — runs on dedicated thread."""
        while not self._stop.is_set():
            try:
                audio = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                if self.transcription_started:
                    self.transcription_started()

                text = self._transcriber.transcribe(audio)

                # Snapshot under lock to avoid mid-reload tear
                with self._lock:
                    dictionary = self._dictionary
                    text_inserter = self._text_inserter

                if text:
                    text = dictionary.apply(text)
                    if text_inserter:
                        text = text_inserter.process(text)

                if text:
                    with self._lock:
                        self._last_text = text
                    if self.transcription_completed:
                        self.transcription_completed(text)
                    self._output_fn(text)

            except Exception as exc:
                message = str(exc)
                if self.error_occurred:
                    self.error_occurred(message)
                print(f"[ERR] Transcription failed: {message}")
