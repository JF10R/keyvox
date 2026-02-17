"""Tests for the main CLI entrypoint wiring."""
import builtins
import runpy
import sys
import types

import pytest

import keyvox.__main__ as main_mod


def _base_config():
    return {
        "audio": {"sample_rate": 16000, "input_device": "default"},
        "hotkey": {"push_to_talk": "ctrl_r"},
        "output": {
            "auto_paste": True,
            "paste_method": "type",
            "double_tap_to_clipboard": True,
            "double_tap_timeout": 0.5,
        },
        "text_insertion": {"enabled": True},
    }


def test_check_single_instance_importerror_returns_true(monkeypatch):
    orig_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"win32event", "win32api", "winerror"}:
            raise ImportError("missing")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert main_mod._check_single_instance() is True


def test_check_single_instance_returns_false_when_mutex_exists(monkeypatch):
    winerror = types.SimpleNamespace(ERROR_ALREADY_EXISTS=183)
    win32event = types.SimpleNamespace(CreateMutex=lambda *args, **kwargs: object())
    win32api = types.SimpleNamespace(GetLastError=lambda: 183)

    monkeypatch.setitem(__import__("sys").modules, "win32event", win32event)
    monkeypatch.setitem(__import__("sys").modules, "win32api", win32api)
    monkeypatch.setitem(__import__("sys").modules, "winerror", winerror)
    assert main_mod._check_single_instance() is False


def test_check_single_instance_returns_true_when_mutex_new(monkeypatch):
    winerror = types.SimpleNamespace(ERROR_ALREADY_EXISTS=183)
    win32event = types.SimpleNamespace(CreateMutex=lambda *args, **kwargs: object())
    win32api = types.SimpleNamespace(GetLastError=lambda: 0)

    monkeypatch.setitem(__import__("sys").modules, "win32event", win32event)
    monkeypatch.setitem(__import__("sys").modules, "win32api", win32api)
    monkeypatch.setitem(__import__("sys").modules, "winerror", winerror)
    assert main_mod._check_single_instance() is True


def test_main_setup_mode_runs_wizard(monkeypatch):
    called = {"setup": False}
    monkeypatch.setattr(main_mod, "run_wizard", lambda: called.__setitem__("setup", True))
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox", "--setup"])
    main_mod.main()
    assert called["setup"] is True


def test_main_exits_when_already_running(monkeypatch):
    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: False)
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox", "--headless"])
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 1


def test_main_happy_path_initializes_and_runs(monkeypatch):
    cfg = _base_config()
    calls = {}

    class FakeDictionary:
        corrections = {"a": "A"}

        @staticmethod
        def load_from_config(config):
            calls["dict_loaded"] = True
            return FakeDictionary()

    class FakeTextInserter:
        def __init__(self, config, dictionary_corrections):
            calls["text_inserter"] = (config, dictionary_corrections)

    class FakeHotkeyManager:
        def __init__(self, **kwargs):
            calls["hotkey_args"] = kwargs

        def run(self):
            calls["run"] = True

    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: True)
    monkeypatch.setattr(main_mod, "load_config", lambda: cfg)
    monkeypatch.setattr(main_mod, "create_transcriber", lambda config: "TRANSCRIBER")
    monkeypatch.setattr(main_mod, "AudioRecorder", lambda sample_rate, input_device: ("REC", sample_rate, input_device))
    monkeypatch.setattr(main_mod, "DictionaryManager", FakeDictionary)
    monkeypatch.setattr(main_mod, "TextInserter", FakeTextInserter)
    monkeypatch.setattr(main_mod, "HotkeyManager", FakeHotkeyManager)
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox", "--headless"])

    main_mod.main()

    assert calls["dict_loaded"] is True
    assert calls["text_inserter"][1] == {"a": "A"}
    assert calls["hotkey_args"]["hotkey_name"] == "ctrl_r"
    assert calls["run"] is True


def test_main_handles_keyboard_interrupt(monkeypatch):
    cfg = _base_config()

    class FakeDictionary:
        corrections = {}

        @staticmethod
        def load_from_config(config):
            return FakeDictionary()

    class FakeHotkeyManager:
        def __init__(self, **kwargs):
            pass

        def run(self):
            raise KeyboardInterrupt()

    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: True)
    monkeypatch.setattr(main_mod, "load_config", lambda: cfg)
    monkeypatch.setattr(main_mod, "create_transcriber", lambda config: "TRANSCRIBER")
    monkeypatch.setattr(main_mod, "AudioRecorder", lambda sample_rate, input_device: object())
    monkeypatch.setattr(main_mod, "DictionaryManager", FakeDictionary)
    monkeypatch.setattr(main_mod, "TextInserter", lambda config, dictionary_corrections: object())
    monkeypatch.setattr(main_mod, "HotkeyManager", FakeHotkeyManager)
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox", "--headless"])

    # Should not exit with error.
    main_mod.main()


def test_main_server_mode_runs_server_with_port(monkeypatch):
    cfg = _base_config()
    calls = {}

    class FakeServer:
        def __init__(self, config, port):
            calls["config"] = config
            calls["port"] = port

        def run(self):
            calls["run"] = True

    fake_server_mod = types.ModuleType("keyvox.server")
    fake_server_mod.KeyvoxServer = FakeServer

    monkeypatch.setitem(sys.modules, "keyvox.server", fake_server_mod)
    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: True)
    monkeypatch.setattr(main_mod, "load_config", lambda: cfg)
    monkeypatch.setattr(main_mod, "create_transcriber", lambda config: (_ for _ in ()).throw(AssertionError("should not initialize local pipeline in --server mode")))
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox", "--server", "--port", "9999"])

    main_mod.main()

    assert calls["config"] is cfg
    assert calls["port"] == 9999
    assert calls["run"] is True


def test_main_server_mode_missing_websockets_exits_with_hint(monkeypatch, capsys):
    cfg = _base_config()

    class FakeServer:
        def __init__(self, config, port):
            pass

        def run(self):
            raise ModuleNotFoundError("No module named 'websockets'", name="websockets")

    fake_server_mod = types.ModuleType("keyvox.server")
    fake_server_mod.KeyvoxServer = FakeServer

    monkeypatch.setitem(sys.modules, "keyvox.server", fake_server_mod)
    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: True)
    monkeypatch.setattr(main_mod, "load_config", lambda: cfg)
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox", "--server"])

    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    captured = capsys.readouterr()
    assert exc.value.code == 1
    assert "Missing dependency for --server mode: websockets" in captured.out
    assert "pip install -e \".[server]\"" in captured.out


def test_main_gui_mode_initializes_tray_and_shutdowns(monkeypatch):
    cfg = _base_config()
    calls = {
        "run": False,
        "stop": False,
        "tray_show": False,
        "signals": [],
    }

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

        def emit(self, *args, **kwargs):
            for callback in list(self._callbacks):
                callback(*args, **kwargs)

    class FakeApp:
        last_instance = None

        def __init__(self, argv):
            self.aboutToQuit = _Signal()
            self.app_name = None
            self.display_name = None
            FakeApp.last_instance = self

        def setQuitOnLastWindowClosed(self, value):
            return None

        def setApplicationName(self, value):
            self.app_name = value

        def setApplicationDisplayName(self, value):
            self.display_name = value

        def quit(self):
            return None

        def exec(self):
            self.aboutToQuit.emit()
            return 0

    class FakeTraySystem:
        @staticmethod
        def isSystemTrayAvailable():
            return True

    class FakeTimer:
        def __init__(self):
            self.timeout = _Signal()
            self.started_ms = None

        def start(self, ms):
            self.started_ms = ms

    class FakeTrayIcon:
        def show(self):
            calls["tray_show"] = True

        def set_state(self, state):
            return None

        def flash_success(self):
            return None

        def flash_error(self):
            return None

    class FakeHotkeyManager:
        def __init__(self, **kwargs):
            self.recording_started = _Signal()
            self.transcription_started = _Signal()
            self.transcription_completed = _Signal()
            self.error_occurred = _Signal()

        def run(self):
            calls["run"] = True

        def stop(self):
            calls["stop"] = True

    class FakeThread:
        def __init__(self, target, daemon):
            self._target = target

        def start(self):
            self._target()

        def is_alive(self):
            return False

        def join(self, timeout=None):
            return None

    fake_pyside = types.ModuleType("PySide6")
    fake_widgets = types.ModuleType("PySide6.QtWidgets")
    fake_widgets.QApplication = FakeApp
    fake_widgets.QSystemTrayIcon = FakeTraySystem
    fake_core = types.ModuleType("PySide6.QtCore")
    fake_core.QTimer = FakeTimer
    fake_tray_mod = types.ModuleType("keyvox.ui.tray_icon")
    fake_tray_mod.KeyvoxTrayIcon = FakeTrayIcon

    monkeypatch.setitem(sys.modules, "PySide6", fake_pyside)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", fake_widgets)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", fake_core)
    monkeypatch.setitem(sys.modules, "keyvox.ui.tray_icon", fake_tray_mod)
    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: True)
    monkeypatch.setattr(main_mod, "load_config", lambda: cfg)
    monkeypatch.setattr(main_mod, "create_transcriber", lambda config: "TRANSCRIBER")
    monkeypatch.setattr(main_mod, "AudioRecorder", lambda sample_rate, input_device: object())
    monkeypatch.setattr(main_mod, "DictionaryManager", types.SimpleNamespace(load_from_config=lambda config: types.SimpleNamespace(corrections={})))
    monkeypatch.setattr(main_mod, "TextInserter", lambda config, dictionary_corrections: object())
    monkeypatch.setattr(main_mod, "HotkeyManager", FakeHotkeyManager)
    monkeypatch.setattr("threading.Thread", FakeThread)
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox"])

    def _fake_signal(sig, handler):
        calls["signals"].append(sig)
        return None

    monkeypatch.setattr("signal.signal", _fake_signal)

    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 0
    assert calls["tray_show"] is True
    assert calls["run"] is True
    assert calls["stop"] is True
    assert FakeApp.last_instance is not None
    assert FakeApp.last_instance.app_name == "Keyvox"
    assert FakeApp.last_instance.display_name == "Keyvox"


def test_main_gui_creates_qapp_before_tray_availability_check(monkeypatch):
    cfg = _base_config()
    state = {"app_created": False, "tray_checked": False, "ran_headless": False}

    class _Signal:
        def __init__(self):
            self._callbacks = []

        def connect(self, callback):
            self._callbacks.append(callback)

    class FakeApp:
        def __init__(self, argv):
            state["app_created"] = True
            self.aboutToQuit = _Signal()
            self.app_name = None
            self.display_name = None

        def setQuitOnLastWindowClosed(self, value):
            return None

        def setApplicationName(self, value):
            self.app_name = value

        def setApplicationDisplayName(self, value):
            self.display_name = value

        def exec(self):
            return 0

    class FakeTraySystem:
        @staticmethod
        def isSystemTrayAvailable():
            # Regression guard: this must run after QApplication construction.
            assert state["app_created"] is True
            state["tray_checked"] = True
            return False

    class FakeHotkeyManager:
        def __init__(self, **kwargs):
            self.recording_started = _Signal()
            self.transcription_started = _Signal()
            self.transcription_completed = _Signal()
            self.error_occurred = _Signal()

        def run(self):
            state["ran_headless"] = True

    fake_pyside = types.ModuleType("PySide6")
    fake_widgets = types.ModuleType("PySide6.QtWidgets")
    fake_widgets.QApplication = FakeApp
    fake_widgets.QSystemTrayIcon = FakeTraySystem
    fake_core = types.ModuleType("PySide6.QtCore")
    fake_core.QTimer = object
    fake_tray_mod = types.ModuleType("keyvox.ui.tray_icon")
    fake_tray_mod.KeyvoxTrayIcon = object

    monkeypatch.setitem(sys.modules, "PySide6", fake_pyside)
    monkeypatch.setitem(sys.modules, "PySide6.QtWidgets", fake_widgets)
    monkeypatch.setitem(sys.modules, "PySide6.QtCore", fake_core)
    monkeypatch.setitem(sys.modules, "keyvox.ui.tray_icon", fake_tray_mod)
    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: True)
    monkeypatch.setattr(main_mod, "load_config", lambda: cfg)
    monkeypatch.setattr(main_mod, "create_transcriber", lambda config: "TRANSCRIBER")
    monkeypatch.setattr(main_mod, "AudioRecorder", lambda sample_rate, input_device: object())
    monkeypatch.setattr(main_mod, "DictionaryManager", types.SimpleNamespace(load_from_config=lambda config: types.SimpleNamespace(corrections={})))
    monkeypatch.setattr(main_mod, "TextInserter", lambda config, dictionary_corrections: object())
    monkeypatch.setattr(main_mod, "HotkeyManager", FakeHotkeyManager)
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox"])

    main_mod.main()
    assert state["tray_checked"] is True
    assert state["ran_headless"] is True


def test_main_handles_fatal_exception(monkeypatch):
    monkeypatch.setattr(main_mod, "_check_single_instance", lambda: True)
    monkeypatch.setattr(main_mod, "load_config", lambda: _base_config())
    monkeypatch.setattr(main_mod, "create_transcriber", lambda config: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox"])

    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 1


def test_module_main_guard_executes_main(monkeypatch):
    from keyvox import setup_wizard as setup_mod

    called = {"setup": False}
    monkeypatch.setattr(setup_mod, "run_wizard", lambda: called.__setitem__("setup", True))
    monkeypatch.setattr(sys, "argv", ["keyvox", "--setup"])
    monkeypatch.delitem(sys.modules, "keyvox.__main__", raising=False)

    runpy.run_module("keyvox.__main__", run_name="__main__")
    assert called["setup"] is True

