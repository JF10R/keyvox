"""Hotkey management and event handling."""
from pynput import keyboard
from pynput.keyboard import Key, Controller
import pyperclip
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .recorder import AudioRecorder
    from .backends import TranscriberBackend


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
        auto_paste: bool = True,
        paste_method: str = "type",
        double_tap_to_clipboard: bool = True,
        double_tap_timeout: float = 0.5
    ):
        self.hotkey = HOTKEY_MAP.get(hotkey_name.lower(), Key.ctrl_r)
        self.recorder = recorder
        self.transcriber = transcriber
        self.auto_paste = auto_paste
        self.paste_method = paste_method
        self.kb = Controller()

        # Double-tap tracking
        self.double_tap_enabled = double_tap_to_clipboard and paste_method == "type"
        self.double_tap_timeout = double_tap_timeout
        self.last_release_time = 0.0
        self.last_transcription = ""

    def _on_press(self, key):
        """Handle key press events."""
        if key == self.hotkey:
            self.recorder.start()

    def _on_release(self, key):
        """Handle key release events."""
        if key == self.hotkey:
            current_time = time.time()

            # Stop recording and get audio
            audio = self.recorder.stop()

            # Check for double-tap (only if enabled)
            if self.double_tap_enabled:
                time_since_last_release = current_time - self.last_release_time

                # Double-tap detected: quick tap with minimal/no audio
                if 0 < time_since_last_release < self.double_tap_timeout:
                    if self.last_transcription:
                        pyperclip.copy(self.last_transcription)
                        print("[OK] Double-tap detected - Last transcription copied to clipboard")
                        self.last_release_time = 0.0  # Reset to prevent triple-tap
                        return
                    else:
                        print("[INFO] Double-tap detected but no previous transcription available")
                        self.last_release_time = 0.0
                        return

            # Transcribe (skip if no audio captured)
            if audio is None:
                return

            text = self.transcriber.transcribe(audio)

            # Update last transcription and release time
            if text:
                if self.double_tap_enabled:
                    self.last_transcription = text
                    self.last_release_time = current_time

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
            print(f"[INFO] Double-tap {self._hotkey_display_name()} to copy last transcription to clipboard")
        print("[INFO] Press ESC to quit\n")

        with keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        ) as listener:
            listener.join()

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
