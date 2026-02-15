"""Shutdown behavior tests for HotkeyManager."""
from pynput.keyboard import Key

from keyvox.hotkey import HotkeyManager


class _DummyRecorder:
    is_recording = False

    def start(self):
        return None

    def stop(self):
        return None


class _DummyTranscriber:
    def transcribe(self, audio):
        return ""


class _DummyDictionary:
    corrections = {}

    def apply(self, text):
        return text

    @staticmethod
    def load_from_config(config_dict):
        return _DummyDictionary()


def _make_manager() -> HotkeyManager:
    return HotkeyManager(
        hotkey_name="ctrl_r",
        recorder=_DummyRecorder(),
        transcriber=_DummyTranscriber(),
        dictionary=_DummyDictionary(),
        text_inserter=None,
    )


def test_escape_release_stops_listener():
    """ESC should immediately stop the listener loop."""
    manager = _make_manager()
    assert manager._on_release(Key.esc) is False


def test_ctrl_c_interrupt_stops_listener(monkeypatch):
    """Ctrl+C during run loop should stop listener and return cleanly."""
    manager = _make_manager()

    class FakeListener:
        last_instance = None

        def __init__(self, on_press, on_release):
            self.on_press = on_press
            self.on_release = on_release
            self._alive = True
            self.stopped = False
            FakeListener.last_instance = self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def is_alive(self):
            return self._alive

        def join(self, timeout=None):
            raise KeyboardInterrupt()

        def stop(self):
            self._alive = False
            self.stopped = True

    monkeypatch.setattr("keyvox.hotkey.keyboard.Listener", FakeListener)

    manager.run()

    assert FakeListener.last_instance is not None
    assert FakeListener.last_instance.stopped is True
