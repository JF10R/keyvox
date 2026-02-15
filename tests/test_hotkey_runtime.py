"""Runtime behavior tests for hotkey workflow and paste logic."""
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


class _Transcriber:
    def __init__(self, result=""):
        self.result = result
        self.calls = 0

    def transcribe(self, audio):
        self.calls += 1
        return self.result


class _Dictionary:
    def __init__(self, prefix=""):
        self.prefix = prefix
        self.corrections = {}
        self.applied = []

    def apply(self, text):
        self.applied.append(text)
        return f"{self.prefix}{text}"

    @staticmethod
    def load_from_config(config):
        inst = _Dictionary(prefix="R:")
        inst.corrections = {"x": "X"}
        return inst


class _TextInserter:
    def __init__(self, config=None, dictionary_corrections=None):
        self.config = config or {}
        self.dictionary_corrections = dictionary_corrections or {}
        self.inputs = []

    def process(self, text):
        self.inputs.append(text)
        return f"P:{text}"


class _KB:
    def __init__(self):
        self.actions = []

    def press(self, key):
        self.actions.append(("press", key))

    def release(self, key):
        self.actions.append(("release", key))

    def type(self, text):
        self.actions.append(("type", text))


def _make_manager(**kwargs) -> HotkeyManager:
    recorder = kwargs.pop("recorder", _Recorder())
    transcriber = kwargs.pop("transcriber", _Transcriber(""))
    dictionary = kwargs.pop("dictionary", _Dictionary())
    manager = HotkeyManager(
        hotkey_name=kwargs.pop("hotkey_name", "ctrl_r"),
        recorder=recorder,
        transcriber=transcriber,
        dictionary=dictionary,
        auto_paste=kwargs.pop("auto_paste", True),
        paste_method=kwargs.pop("paste_method", "type"),
        double_tap_to_clipboard=kwargs.pop("double_tap_to_clipboard", True),
        double_tap_timeout=kwargs.pop("double_tap_timeout", 0.5),
        text_inserter=kwargs.pop("text_inserter", _TextInserter()),
    )
    manager.kb = _KB()
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
    manager = _make_manager(transcriber=_Transcriber("hello"))
    manager.recorder.stop_value = None
    manager.last_press_time = 0
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 1.0)
    manager._on_release(manager.hotkey)
    assert manager.transcriber.calls == 0


def test_on_release_skips_short_recordings(monkeypatch):
    manager = _make_manager(transcriber=_Transcriber("hello"))
    manager.recorder.stop_value = np.array([0.1], dtype=np.float32)
    manager.last_press_time = 10.0
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 10.1)
    manager._on_release(manager.hotkey)
    assert manager.transcriber.calls == 0
    assert manager.last_release_time == 10.1


def test_on_release_double_tap_pastes_last_transcription(monkeypatch):
    copied = []
    monkeypatch.setattr(hotkey_module.pyperclip, "copy", lambda t: copied.append(t))

    manager = _make_manager()
    manager.last_transcription = "last-text"
    manager.last_release_time = 10.0
    manager.last_press_time = 0.0
    manager.recorder.stop_value = None
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 10.2)

    manager._on_release(manager.hotkey)

    assert copied == ["last-text"]
    assert ("press", Key.ctrl) in manager.kb.actions
    assert ("press", "v") in manager.kb.actions
    assert manager.last_release_time == 0.0


def test_on_release_double_tap_without_previous_transcription(monkeypatch):
    copied = []
    monkeypatch.setattr(hotkey_module.pyperclip, "copy", lambda t: copied.append(t))

    manager = _make_manager()
    manager.last_transcription = ""
    manager.last_release_time = 10.0
    manager.last_press_time = 0.0
    manager.recorder.stop_value = None
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 10.2)

    manager._on_release(manager.hotkey)

    assert copied == []
    assert manager.last_release_time == 0.0


def test_on_release_transcribes_applies_processing_and_copies_when_auto_paste_disabled(monkeypatch):
    copied = []
    monkeypatch.setattr(hotkey_module.pyperclip, "copy", lambda t: copied.append(t))
    monkeypatch.setattr(hotkey_module, "GUI_AVAILABLE", False)

    transcriber = _Transcriber("hello")
    dictionary = _Dictionary(prefix="D:")
    inserter = _TextInserter()
    manager = _make_manager(
        transcriber=transcriber,
        dictionary=dictionary,
        text_inserter=inserter,
        auto_paste=False,
    )
    manager.recorder.stop_value = np.array([0.1, 0.2], dtype=np.float32)
    manager.last_press_time = 0.0
    manager.last_release_time = 0.0
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 1.0)

    manager._on_release(manager.hotkey)

    assert transcriber.calls == 1
    assert dictionary.applied == ["hello"]
    assert inserter.inputs == ["D:hello"]
    assert copied == ["P:D:hello"]
    assert manager.last_transcription == "P:D:hello"


def test_on_release_uses_paste_when_auto_paste_enabled(monkeypatch):
    monkeypatch.setattr(hotkey_module, "GUI_AVAILABLE", False)
    transcriber = _Transcriber("hello")
    manager = _make_manager(
        transcriber=transcriber,
        dictionary=_Dictionary(prefix="D:"),
        text_inserter=_TextInserter(),
        auto_paste=True,
    )
    pasted = []
    manager._paste_text = lambda text: pasted.append(text)
    manager.recorder.stop_value = np.array([0.1, 0.2], dtype=np.float32)
    manager.last_press_time = 0.0
    monkeypatch.setattr(hotkey_module.time, "time", lambda: 1.0)

    manager._on_release(manager.hotkey)
    assert pasted == ["P:D:hello"]


def test_paste_text_type_mode():
    manager = _make_manager(paste_method="type")
    manager._paste_text("abc")
    assert ("type", "abc") in manager.kb.actions


def test_paste_text_clipboard_mode(monkeypatch):
    copied = []
    monkeypatch.setattr(hotkey_module.pyperclip, "copy", lambda t: copied.append(t))
    manager = _make_manager(paste_method="clipboard")
    manager._paste_text("abc")
    assert copied == ["abc"]
    assert ("press", Key.ctrl) in manager.kb.actions
    assert ("press", "v") in manager.kb.actions


def test_paste_text_clipboard_restore_mode(monkeypatch):
    copied = []
    monkeypatch.setattr(hotkey_module.pyperclip, "paste", lambda: "old")
    monkeypatch.setattr(hotkey_module.pyperclip, "copy", lambda t: copied.append(t))
    manager = _make_manager(paste_method="clipboard-restore")
    manager._paste_text("new")
    assert copied == ["new", "old"]


def test_paste_text_unknown_mode_falls_back_to_type():
    manager = _make_manager(paste_method="invalid")
    manager._paste_text("abc")
    assert ("type", "abc") in manager.kb.actions


def test_hotkey_display_name_fallback_for_unknown():
    manager = _make_manager(hotkey_name="unknown-hotkey")
    # Force a non-mapped key object.
    manager.hotkey = object()
    assert manager._hotkey_display_name() == "CTRL_R"


def test_maybe_reload_runtime_config_none_does_nothing():
    manager = _make_manager()
    manager._config_reloader = types.SimpleNamespace(poll=lambda: None)
    before_dict = manager.dictionary
    before_inserter = manager.text_inserter
    manager._maybe_reload_runtime_config()
    assert manager.dictionary is before_dict
    assert manager.text_inserter is before_inserter


def test_maybe_reload_runtime_config_exception_does_not_raise():
    manager = _make_manager()

    def boom():
        raise RuntimeError("bad config")

    manager._config_reloader = types.SimpleNamespace(poll=boom)
    manager._maybe_reload_runtime_config()


def test_maybe_reload_runtime_config_replaces_dictionary_and_inserter():
    manager = _make_manager(dictionary=_Dictionary(), text_inserter=_TextInserter())
    manager._config_reloader = types.SimpleNamespace(poll=lambda: {"text_insertion": {"enabled": True}})
    manager._maybe_reload_runtime_config()
    assert isinstance(manager.dictionary, _Dictionary)
    assert manager.dictionary.prefix == "R:"
    assert isinstance(manager.text_inserter, _TextInserter)
    assert manager.text_inserter.dictionary_corrections == {"x": "X"}


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
