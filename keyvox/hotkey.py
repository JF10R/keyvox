"""Hotkey management and event handling."""
import ctypes
import os
import sys
import threading
from pynput import keyboard
from pynput.keyboard import Key
import time
from typing import TYPE_CHECKING, Callable, List, Optional
from .config import get_config_path, load_config
from .config_reload import FileReloader

if TYPE_CHECKING:
    from .recorder import AudioRecorder
    from .pipeline import TranscriptionPipeline


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


class HotkeyManager(object):
    """Manages keyboard hotkeys; delegates transcription to TranscriptionPipeline."""

    def __init__(
        self,
        hotkey_name: str,
        recorder: "AudioRecorder",
        pipeline: "TranscriptionPipeline",
        double_tap_timeout: float = 0.5,
    ):
        self.hotkey = HOTKEY_MAP.get(hotkey_name.lower(), Key.ctrl_r)
        self.recorder = recorder
        self._pipeline = pipeline
        self.double_tap_timeout = double_tap_timeout

        # Double-tap tracking
        self.last_release_time = 0.0
        self.last_press_time = 0.0

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

        # Per-instance subscriber lists.
        self.recording_started = _CallbackSignal()
        self.recording_stopped = _CallbackSignal()

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

            # Double-tap: release within timeout window of previous release
            time_since_last_release = current_time - self.last_release_time
            if 0 < time_since_last_release < self.double_tap_timeout:
                self._pipeline.replay_last()
                self.last_release_time = 0.0  # Reset to prevent triple-tap
                return

            if audio is None:
                return

            # Skip very short recordings (likely accidental taps)
            # Minimum 0.3s to avoid Whisper hallucinations on silence
            if recording_duration < 0.3:
                print(f"[INFO] Recording too short ({recording_duration:.2f}s) - skipped")
                self.last_release_time = current_time
                return

            self.last_release_time = current_time
            self._pipeline.enqueue(audio)  # returns immediately (<1ms)

        elif key == Key.esc:
            if self.escape_shutdown_enabled and self._is_own_console_focused():
                print("\n[INFO] Shutting down...")
                self._stop_requested.set()
                return False  # Stop listener

    def run(self) -> None:
        """Start the hotkey listener (blocking)."""
        self._stop_requested.clear()
        print(f"[OK] Push-to-Talk enabled - Hold {self._hotkey_display_name()} to speak")
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

        self._pipeline.reload_config(updated_config)

    def _hotkey_display_name(self) -> str:
        """Get display name for hotkey."""
        for name, key in HOTKEY_MAP.items():
            if key == self.hotkey:
                return name.upper()
        return "CTRL_R"
