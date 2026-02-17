"""Hotkey management and event handling."""
import ctypes
import os
import sys
import threading
from pynput import keyboard
from pynput.keyboard import Key, Controller
import pyperclip
import time
from typing import TYPE_CHECKING, Callable, List, Optional
from .config import get_config_path, load_config
from .config_reload import FileReloader

if TYPE_CHECKING:
    from .recorder import AudioRecorder
    from .backends import TranscriberBackend
    from .dictionary import DictionaryManager
    from .text_insertion import TextInserter

# --- Qt-optional base class ---
# When PySide6 is available, HotkeyManager inherits QObject and exposes
# real Qt Signals.  When it isn't (headless / server mode), we fall back
# to a lightweight stub so the rest of the code doesn't need to care.

try:
    from PySide6.QtCore import QObject, Signal as _QtSignal

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


class _CallbackSignal:
    """Minimal Signal replacement: register callbacks, emit fires them all."""

    def __init__(self):
        self._callbacks: List[Callable] = []

    def connect(self, fn: Callable) -> None:
        self._callbacks.append(fn)

    def disconnect(self, fn: Callable | None = None) -> None:
        if fn is None:
            self._callbacks.clear()
        else:
            self._callbacks = [cb for cb in self._callbacks if cb is not fn]

    def emit(self, *args) -> None:
        for cb in self._callbacks:
            cb(*args)


if _HAS_QT:
    _Base = QObject

    def _make_signal(*types):
        return _QtSignal(*types) if types else _QtSignal()
else:
    _Base = object

    def _make_signal(*_types):
        return _CallbackSignal()


# Lazy import for GUI mode (TranscriptionWorker uses Qt)
try:
    from .ui.transcription_worker import TranscriptionWorker
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False


# Mapping of string hotkey names to pynput Key objects
HOTKEY_MAP = {
    "ctrl_r": Key.ctrl_r,
    "ctrl_l": Key.ctrl_l,
    "alt_r": Key.alt_r,
    "alt_l": Key.alt_l,
    "shift_r": Key.shift_r,
    "shift_l": Key.shift_l,
    "cmd": Key.cmd,
    "cmd_r": Key.cmd_r,
    "cmd_l": Key.cmd_l,
}


class HotkeyManager(_Base):
    """Manages keyboard hotkeys and transcription workflow."""

    # Qt signals for UI integration (or lightweight callbacks when Qt absent)
    recording_started = _make_signal()
    recording_stopped = _make_signal()
    transcription_started = _make_signal()
    transcription_completed = _make_signal(str)
    error_occurred = _make_signal(str)

    def __init__(
        self,
        hotkey_name: str,
        recorder: "AudioRecorder",
        transcriber: "TranscriberBackend",
        dictionary: "DictionaryManager",
        auto_paste: bool = True,
        paste_method: str = "type",
        double_tap_to_clipboard: bool = True,
        double_tap_timeout: float = 0.5,
        text_inserter: Optional["TextInserter"] = None
    ):
        if _HAS_QT:
            super().__init__()
        self.hotkey = HOTKEY_MAP.get(hotkey_name.lower(), Key.ctrl_r)
        self.recorder = recorder
        self.transcriber = transcriber
        self.dictionary = dictionary
        self.auto_paste = auto_paste
        self.paste_method = paste_method
        self.text_inserter = text_inserter
        self.kb = Controller()

        # Double-tap tracking
        self.double_tap_enabled = double_tap_to_clipboard and paste_method == "type"
        self.double_tap_timeout = double_tap_timeout
        self.last_release_time = 0.0
        self.last_transcription = ""
        self.last_press_time = 0.0
        # Processing flag to prevent overlapping transcriptions
        self.is_processing = False
        # Windows Terminal uses global hooks + tabbed host, so ESC quit is unsafe.
        self.escape_shutdown_enabled = os.getenv("WT_SESSION") is None
        self._config_reloader = FileReloader(
            path_getter=get_config_path,
            loader=lambda path: load_config(path=path, quiet=True, raise_on_error=True),
            min_interval_s=0.5,
        )
        self._config_reloader.prime()
        self._listener: Optional[keyboard.Listener] = None
        self._stop_requested = threading.Event()

        # When Qt is not available, _CallbackSignal instances are per-class
        # descriptors.  We need per-instance copies so each instance has its
        # own subscriber list.
        if not _HAS_QT:
            self.recording_started = _CallbackSignal()
            self.recording_stopped = _CallbackSignal()
            self.transcription_started = _CallbackSignal()
            self.transcription_completed = _CallbackSignal()
            self.error_occurred = _CallbackSignal()

    def _on_press(self, key):
        """Handle key press events."""
        if key == self.hotkey:
            # Only update timestamp if we're actually starting a new recording
            # (ignore key repeat events)
            if not self.recorder.is_recording:
                self.last_press_time = time.time()
                self.recording_started.emit()
            self.recorder.start()

    def _on_release(self, key):
        """Handle key release events."""
        if key == self.hotkey:
            current_time = time.time()
            self._maybe_reload_runtime_config()

            # Stop recording and get audio
            audio = self.recorder.stop()
            self.recording_stopped.emit()

            # Calculate recording duration
            recording_duration = current_time - self.last_press_time

            # Check for double-tap (only if enabled)
            if self.double_tap_enabled:
                time_since_last_release = current_time - self.last_release_time

                # Double-tap detected: copy last transcription to clipboard and paste it
                if 0 < time_since_last_release < self.double_tap_timeout:
                    if self.last_transcription:
                        pyperclip.copy(self.last_transcription)
                        self.kb.press(Key.ctrl)
                        self.kb.press('v')
                        self.kb.release('v')
                        self.kb.release(Key.ctrl)
                        print("[OK] Double-tap detected - Last transcription pasted")
                        self.last_release_time = 0.0  # Reset to prevent triple-tap
                        return
                    else:
                        print("[INFO] Double-tap detected but no previous transcription available")
                        self.last_release_time = 0.0
                        return

            # Transcribe (skip if no audio captured)
            if audio is None:
                return

            # Skip very short recordings (likely accidental taps)
            # Minimum 0.3s to avoid Whisper hallucinations on silence
            if recording_duration < 0.3:
                print(f"[INFO] Recording too short ({recording_duration:.2f}s) - skipped")
                # Still update last_release_time for double-tap detection
                if self.double_tap_enabled:
                    self.last_release_time = current_time
                return

            # Prevent overlapping transcriptions
            if self.is_processing:
                print("[WARN] Already processing, skipping this recording")
                return

            # Update last release time for double-tap detection (even if transcription is empty)
            if self.double_tap_enabled:
                self.last_release_time = current_time

            # Non-blocking transcription (GUI mode) or blocking (headless mode)
            if GUI_AVAILABLE:
                self.is_processing = True
                self.transcription_started.emit()

                worker = TranscriptionWorker(audio, self.transcriber, self.dictionary, self.text_inserter)
                worker.signals.completed.connect(self._on_transcription_done)
                worker.signals.error.connect(self._on_transcription_error)
                QThreadPool.globalInstance().start(worker)
            else:
                # Headless mode: blocking transcription (original behavior)
                self.transcription_started.emit()
                text = self.transcriber.transcribe(audio)

                # Apply dictionary corrections
                if text:
                    text = self.dictionary.apply(text)

                    # Apply smart text insertion
                    if self.text_inserter:
                        text = self.text_inserter.process(text)

                # Update last transcription (after all processing)
                if text:
                    if self.double_tap_enabled:
                        self.last_transcription = text

                    self.transcription_completed.emit(text)

                    # Paste or copy transcription
                    if self.auto_paste:
                        self._paste_text(text)
                    else:
                        pyperclip.copy(text)
                        print("[OK] Text copied to clipboard")

        elif key == Key.esc:
            if self.escape_shutdown_enabled and self._is_own_console_focused():
                print("\n[INFO] Shutting down...")
                self._stop_requested.set()
                return False  # Stop listener

    def run(self) -> None:
        """Start the hotkey listener (blocking)."""
        self._stop_requested.clear()
        print(f"[OK] Push-to-Talk enabled - Hold {self._hotkey_display_name()} to speak")
        if self.double_tap_enabled:
            print(f"[INFO] Double-tap {self._hotkey_display_name()} to paste last transcription")
        if self.escape_shutdown_enabled:
            print("[INFO] Press ESC (Keyvox terminal focused) or Ctrl+C to quit\n")
        else:
            print("[INFO] Press Ctrl+C to quit (ESC disabled in Windows Terminal)\n")

        with keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        ) as listener:
            self._listener = listener
            try:
                # Timed join keeps the main thread responsive to Ctrl+C.
                while listener.is_alive() and not self._stop_requested.is_set():
                    listener.join(0.2)
            except KeyboardInterrupt:
                print("\n[INFO] Interrupted by user, shutting down...")
                self._stop_requested.set()
                listener.stop()
                deadline = time.monotonic() + 1.0
                while listener.is_alive() and time.monotonic() < deadline:
                    try:
                        listener.join(0.05)
                    except KeyboardInterrupt:
                        print("[WARN] Force exiting now.")
                        raise SystemExit(130)
                if listener.is_alive():
                    print("[WARN] Listener is busy. Press Ctrl+C again to force exit.")
                    while listener.is_alive():
                        try:
                            listener.join(0.2)
                        except KeyboardInterrupt:
                            print("[WARN] Force exiting now.")
                            raise SystemExit(130)
            finally:
                self._listener = None

    def stop(self) -> None:
        """Request listener shutdown from another thread/event loop."""
        self._stop_requested.set()
        listener = self._listener
        if listener is not None:
            listener.stop()

    def _is_own_console_focused(self) -> bool:
        """Return True when this Keyvox console window is currently focused."""
        if sys.platform != "win32":
            return True

        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            console_hwnd = kernel32.GetConsoleWindow()
            if not console_hwnd:
                return False
            return user32.GetForegroundWindow() == console_hwnd
        except Exception:
            # Conservative fallback: do not allow global ESC shutdown.
            return False

    def _maybe_reload_runtime_config(self) -> None:
        """Hot-reload dictionary/text insertion settings when config changes."""
        try:
            updated_config = self._config_reloader.poll()
        except Exception as e:
            print(f"[WARN] Config hot-reload skipped: {e}")
            return

        if updated_config is None:
            return

        self.dictionary = self.dictionary.__class__.load_from_config(updated_config)
        if self.text_inserter:
            self.text_inserter = self.text_inserter.__class__(
                config=updated_config.get("text_insertion", {}),
                dictionary_corrections=self.dictionary.corrections,
            )
        print("[INFO] Hot-reloaded config: dictionary/text_insertion")

    def _paste_text(self, text: str) -> None:
        """Paste text using the configured method."""
        if self.paste_method == "type":
            # Method 1: Simulate typing (no clipboard interaction)
            self.kb.type(text)
            print("[OK] Text typed")

        elif self.paste_method == "clipboard":
            # Method 2: Paste via Ctrl+V (uses clipboard briefly)
            pyperclip.copy(text)
            self.kb.press(Key.ctrl)
            self.kb.press('v')
            self.kb.release('v')
            self.kb.release(Key.ctrl)
            print("[OK] Text pasted via clipboard")

        elif self.paste_method == "clipboard-restore":
            # Method 3: Paste via Ctrl+V, then restore old clipboard
            old_clipboard = pyperclip.paste()
            pyperclip.copy(text)
            self.kb.press(Key.ctrl)
            self.kb.press('v')
            self.kb.release('v')
            self.kb.release(Key.ctrl)
            pyperclip.copy(old_clipboard)
            print("[OK] Text pasted (clipboard restored)")

        else:
            # Fallback to typing if unknown method
            print(f"[WARN] Unknown paste_method '{self.paste_method}', falling back to 'type'")
            self.kb.type(text)
            print("[OK] Text typed")

    def _hotkey_display_name(self) -> str:
        """Get display name for hotkey."""
        for name, key in HOTKEY_MAP.items():
            if key == self.hotkey:
                return name.upper()
        return "CTRL_R"

    def _on_transcription_done(self, text: str) -> None:
        """Handle transcription completion (called in main thread via Qt signal).

        Args:
            text: Transcribed and processed text from worker
        """
        self.is_processing = False
        self.transcription_completed.emit(text)

        # Update last transcription (worker already applied dictionary/text_inserter)
        if text:
            if self.double_tap_enabled:
                self.last_transcription = text

            # Paste or copy transcription
            if self.auto_paste:
                self._paste_text(text)
            else:
                pyperclip.copy(text)
                print("[OK] Text copied to clipboard")

    def _on_transcription_error(self, error_msg: str) -> None:
        """Handle transcription error (called in main thread via Qt signal).

        Args:
            error_msg: Error message from worker
        """
        self.is_processing = False
        self.error_occurred.emit(error_msg)
        print(f"[ERR] Transcription failed: {error_msg}")
