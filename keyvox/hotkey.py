"""Hotkey management and event handling."""
from pynput import keyboard
from pynput.keyboard import Key, Controller
import pyperclip
import time
from typing import TYPE_CHECKING, Optional
from .config import get_config_path, load_config
from .config_reload import FileReloader

if TYPE_CHECKING:
    from .recorder import AudioRecorder
    from .backends import TranscriberBackend
    from .dictionary import DictionaryManager
    from .text_insertion import TextInserter


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


class HotkeyManager:
    """Manages keyboard hotkeys and transcription workflow."""

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
        self._config_reloader = FileReloader(
            path_getter=get_config_path,
            loader=lambda path: load_config(path=path, quiet=True, raise_on_error=True),
            min_interval_s=0.5,
        )
        self._config_reloader.prime()

    def _on_press(self, key):
        """Handle key press events."""
        if key == self.hotkey:
            # Only update timestamp if we're actually starting a new recording
            # (ignore key repeat events)
            if not self.recorder.is_recording:
                self.last_press_time = time.time()
            self.recorder.start()

    def _on_release(self, key):
        """Handle key release events."""
        if key == self.hotkey:
            current_time = time.time()
            self._maybe_reload_runtime_config()

            # Stop recording and get audio
            audio = self.recorder.stop()

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

            # Update last release time for double-tap detection (even if transcription is empty)
            if self.double_tap_enabled:
                self.last_release_time = current_time

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

                # Paste or copy transcription
                if self.auto_paste:
                    self._paste_text(text)
                else:
                    pyperclip.copy(text)
                    print("[OK] Text copied to clipboard")

        elif key == Key.esc:
            print("\n[INFO] Shutting down...")
            return False  # Stop listener

    def run(self) -> None:
        """Start the hotkey listener (blocking)."""
        print(f"[OK] Push-to-Talk enabled - Hold {self._hotkey_display_name()} to speak")
        if self.double_tap_enabled:
            print(f"[INFO] Double-tap {self._hotkey_display_name()} to paste last transcription")
        print("[INFO] Press ESC or Ctrl+C to quit\n")

        with keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        ) as listener:
            try:
                # Timed join keeps the main thread responsive to Ctrl+C.
                while listener.is_alive():
                    listener.join(0.2)
            except KeyboardInterrupt:
                print("\n[INFO] Interrupted by user, shutting down...")
                listener.stop()

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
