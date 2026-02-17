"""Runtime behavior tests for HotkeyManager (listener layer only)."""
import types

import numpy as np
from pynput.keyboard import Key

import keyvox.hotkey as hotkey_module
from keyvox.hotkey import HotkeyManager


class _Recorder:
    def __init__(self):
        self.is_recording = False
        self.started = 0
        self.stop_value = None

    def start(self):
        self.started += 1
        self.is_recording = True

    def stop(self):
        self.is_recording = False
        return self.stop_value


class _Pipeline:
    def __init__(self):
        self.enqueued = []
        self.replayed = 0
        self.reloaded = []

    def enqueue(self, audio):
        self.enqueued.append(audio)

    def replay_last(self):
        self.replayed += 1

    def reload_config(self, config):
        self.reloaded.append(config)


def _make_manager(**kwargs) -> HotkeyManager:
    recorder = kwargs.pop("recorder", _Recorder())
    pipeline = kwargs.pop("pipeline", _Pipeline())
    manager = HotkeyManager(
        hotkey_name=kwargs.pop("hotkey_name", "ctrl_r"),
        recorder=recorder,
        pipeline=pipeline,
        double_tap_timeout=kwargs.pop("double_tap_timeout", 0.5),
    )
    return manager


def test_on_press_updates_timestamp_only_when_not_recording(monkeypatch):
    manager = _make_manager()
    times = iter([10.0, 20.0])
    monkeypatch.setattr(hotkey_module.time, "time", lambda: next(times))

    manager.recorder.is_recording = False
    manager._on_press(manager.hotkey)
    first = manager.last_press_time

    manager.recorder.is_recording = True
    manager._on_press(manager.hotkey)
    assert manager.last_press_time == first
    assert manager.recorder.started == 2


def test_on_release_returns_early_when_no_audio(monkeypatch):
    pipeline = _Pipeline()
    manager = _make_manager(pipeline=pipeline)
    manager.recorder.stop_value = None
    manager.last_press_time = 0
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 1.0)
    manager._on_release(manager.hotkey)
    assert pipeline.enqueued == []


def test_on_release_skips_short_recordings(monkeypatch):
    pipeline = _Pipeline()
    manager = _make_manager(pipeline=pipeline)
    manager.recorder.stop_value = np.array([0.1], dtype=np.float32)
    manager.last_press_time = 10.0
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 10.1)
    manager._on_release(manager.hotkey)
    assert pipeline.enqueued == []
    assert manager.last_release_time == 10.1


def test_on_release_enqueues_audio_on_pipeline(monkeypatch):
    pipeline = _Pipeline()
    manager = _make_manager(pipeline=pipeline)
    audio = np.array([0.1, 0.2], dtype=np.float32)
    manager.recorder.stop_value = audio
    manager.last_press_time = 0.0
    manager.last_release_time = 0.0
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 1.0)

    manager._on_release(manager.hotkey)

    assert len(pipeline.enqueued) == 1
    assert manager.last_release_time == 1.0


def test_on_release_double_tap_calls_replay_last(monkeypatch):
    pipeline = _Pipeline()
    manager = _make_manager(pipeline=pipeline)
    manager.last_release_time = 10.0
    manager.last_press_time = 0.0
    manager.recorder.stop_value = None
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 10.2)

    manager._on_release(manager.hotkey)

    assert pipeline.replayed == 1
    assert manager.last_release_time == 0.0  # Reset to prevent triple-tap


def test_on_release_double_tap_resets_release_time(monkeypatch):
    pipeline = _Pipeline()
    manager = _make_manager(pipeline=pipeline)
    manager.last_release_time = 10.0
    manager.last_press_time = 0.0
    manager.recorder.stop_value = None
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 10.2)

    manager._on_release(manager.hotkey)

    # Reset prevents a third tap from being treated as double-tap
    assert manager.last_release_time == 0.0


def test_hotkey_display_name_fallback_for_unknown():
    manager = _make_manager(hotkey_name="unknown-hotkey")
    # Force a non-mapped key object.
    manager.hotkey = object()
    assert manager._hotkey_display_name() == "CTRL_R"


def test_maybe_reload_runtime_config_none_does_nothing():
    pipeline = _Pipeline()
    manager = _make_manager(pipeline=pipeline)
    manager._config_reloader = types.SimpleNamespace(poll=lambda: None)
    manager._maybe_reload_runtime_config()
    assert pipeline.reloaded == []


def test_maybe_reload_runtime_config_exception_does_not_raise():
    manager = _make_manager()

    def boom():
        raise RuntimeError("bad config")

    manager._config_reloader = types.SimpleNamespace(poll=boom)
    manager._maybe_reload_runtime_config()  # Must not raise


def test_maybe_reload_runtime_config_calls_pipeline_reload():
    pipeline = _Pipeline()
    manager = _make_manager(pipeline=pipeline)
    new_config = {"text_insertion": {"enabled": True}}
    manager._config_reloader = types.SimpleNamespace(poll=lambda: new_config)
    manager._maybe_reload_runtime_config()
    assert pipeline.reloaded == [new_config]


def test_is_own_console_focused_non_windows(monkeypatch):
    manager = _make_manager()
    monkeypatch.setattr(hotkey_module.sys, "platform", "linux", raising=False)
    assert manager._is_own_console_focused() is True


def test_is_own_console_focused_windows_true(monkeypatch):
    manager = _make_manager()
    monkeypatch.setattr(hotkey_module.sys, "platform", "win32", raising=False)

    class Kernel32:
        @staticmethod
        def GetConsoleWindow():
            return 123

    class User32:
        @staticmethod
        def GetForegroundWindow():
            return 123

    monkeypatch.setattr(hotkey_module.ctypes, "windll", types.SimpleNamespace(user32=User32(), kernel32=Kernel32()))
    assert manager._is_own_console_focused() is True


def test_is_own_console_focused_windows_exception(monkeypatch):
    manager = _make_manager()
    monkeypatch.setattr(hotkey_module.sys, "platform", "win32", raising=False)

    class BadWindll:
        @property
        def user32(self):
            raise RuntimeError("nope")

    monkeypatch.setattr(hotkey_module.ctypes, "windll", BadWindll())
    assert manager._is_own_console_focused() is False


def test_is_own_console_focused_windows_without_console_hwnd(monkeypatch):
    manager = _make_manager()
    monkeypatch.setattr(hotkey_module.sys, "platform", "win32", raising=False)

    class Kernel32:
        @staticmethod
        def GetConsoleWindow():
            return 0

    class User32:
        @staticmethod
        def GetForegroundWindow():
            return 999

    monkeypatch.setattr(
        hotkey_module.ctypes,
        "windll",
        types.SimpleNamespace(user32=User32(), kernel32=Kernel32()),
    )
    assert manager._is_own_console_focused() is False
