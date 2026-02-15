"""Hotkey management and event handling."""
from pynput import keyboard
from pynput.keyboard import Key, Controller
import pyperclip
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .recorder import AudioRecorder
    from .transcriber import Transcriber


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
        transcriber: "Transcriber",
        auto_paste: bool = True
    ):
        self.hotkey = HOTKEY_MAP.get(hotkey_name.lower(), Key.ctrl_r)
        self.recorder = recorder
        self.transcriber = transcriber
        self.auto_paste = auto_paste
        self.kb = Controller()

    def _on_press(self, key):
        """Handle key press events."""
        if key == self.hotkey:
            self.recorder.start()

    def _on_release(self, key):
        """Handle key release events."""
        if key == self.hotkey:
            # Stop recording and get audio
            audio = self.recorder.stop()

            # Transcribe
            text = self.transcriber.transcribe(audio)

            # Copy to clipboard and paste if enabled
            if text:
                pyperclip.copy(text)

                if self.auto_paste:
                    self.kb.press(Key.ctrl)
                    self.kb.press('v')
                    self.kb.release('v')
                    self.kb.release(Key.ctrl)
                    print("[OK] Text pasted")
                else:
                    print("[OK] Text copied to clipboard")

        elif key == Key.esc:
            print("\n[INFO] Shutting down...")
            return False  # Stop listener

    def run(self) -> None:
        """Start the hotkey listener (blocking)."""
        print(f"[OK] Push-to-Talk enabled - Hold {self._hotkey_display_name()} to speak")
        print("[INFO] Press ESC to quit\n")

        with keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release
        ) as listener:
            listener.join()

    def _hotkey_display_name(self) -> str:
        """Get display name for hotkey."""
        for name, key in HOTKEY_MAP.items():
            if key == self.hotkey:
                return name.upper()
        return "CTRL_R"
