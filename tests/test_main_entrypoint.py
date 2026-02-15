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
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox"])
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
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox"])

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
    monkeypatch.setattr(main_mod.sys, "argv", ["keyvox"])

    # Should not exit with error.
    main_mod.main()


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
