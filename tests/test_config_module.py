"""Tests for configuration loading and serialization."""
import pathlib
import sys
from pathlib import Path

from keyvox import config as config_module
import keyvox.config


class _FakePosixPath(pathlib.PurePosixPath):
    @classmethod
    def cwd(cls):
        return cls("/work")

    @classmethod
    def home(cls):
        return cls("/home/tester")


def test_merge_configs_is_recursive():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    overrides = {"a": {"y": 9}, "b": 5}
    result = config_module._merge_configs(base, overrides)
    assert result == {"a": {"x": 1, "y": 9}, "b": 5}


def test_find_config_path_uses_first_existing_dir(monkeypatch, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (second / "config.toml").write_text("[model]\nname='tiny'\n", encoding="utf-8")

    monkeypatch.setattr(config_module, "_config_dirs", lambda: [first, second])
    assert config_module._find_config_path() == second / "config.toml"


def test_find_config_path_returns_none_when_missing(monkeypatch, tmp_path):
    only = tmp_path / "only"
    only.mkdir()
    monkeypatch.setattr(config_module, "_config_dirs", lambda: [only])
    assert config_module._find_config_path() is None


def test_get_config_path_proxies_find(monkeypatch, tmp_path):
    target = tmp_path / "config.toml"
    monkeypatch.setattr(config_module, "_find_config_path", lambda: target)
    assert config_module.get_config_path() == target


def test_load_config_without_file_uses_defaults(monkeypatch):
    monkeypatch.setattr(config_module, "_find_config_path", lambda: None)
    loaded = config_module.load_config(quiet=True)
    assert loaded["model"]["name"] == "large-v3-turbo"
    assert loaded["text_insertion"]["www_mode"] == "explicit_only"


def test_load_config_invalid_file_falls_back_when_not_strict(tmp_path):
    invalid = tmp_path / "config.toml"
    invalid.write_text("[model\nname='broken'\n", encoding="utf-8")
    loaded = config_module.load_config(path=invalid, quiet=True, raise_on_error=False)
    assert loaded["model"]["name"] == "large-v3-turbo"


def test_load_config_prints_loaded_path_when_not_quiet(tmp_path, capsys):
    conf = tmp_path / "config.toml"
    conf.write_text("[model]\nname='tiny'\n", encoding="utf-8")
    loaded = config_module.load_config(path=conf, quiet=False)
    out = capsys.readouterr().out
    assert loaded["model"]["name"] == "tiny"
    assert "Loaded config from" in out


def test_load_config_invalid_file_prints_default_notice_when_not_quiet(tmp_path, capsys):
    invalid = tmp_path / "config.toml"
    invalid.write_text("[model\nname='broken'\n", encoding="utf-8")
    loaded = config_module.load_config(path=invalid, quiet=False, raise_on_error=False)
    out = capsys.readouterr().out
    assert loaded["model"]["name"] == "large-v3-turbo"
    assert "Using default configuration" in out


def test_load_config_no_file_prints_defaults_notice(monkeypatch, capsys):
    monkeypatch.setattr(config_module, "_find_config_path", lambda: None)
    loaded = config_module.load_config(quiet=False)
    out = capsys.readouterr().out
    assert loaded["model"]["name"] == "large-v3-turbo"
    assert "No config.toml found, using defaults" in out


def test_save_config_writes_sections_and_types(tmp_path):
    path = tmp_path / "config.toml"
    content = {
        "model": {"name": "tiny", "device": "cpu", "compute_type": "int8", "backend": "auto"},
        "output": {"auto_paste": True, "double_tap_timeout": 0.5},
    }
    config_module.save_config(path, content)

    raw = path.read_text(encoding="utf-8")
    assert "[model]" in raw
    assert 'name = "tiny"' in raw
    assert "auto_paste = true" in raw
    assert "double_tap_timeout = 0.5" in raw


def test_config_dirs_windows(monkeypatch):
    monkeypatch.setattr(config_module.os, "name", "nt", raising=False)
    monkeypatch.setattr(config_module.sys, "platform", "win32", raising=False)
    monkeypatch.setenv("APPDATA", r"C:\Users\me\AppData\Roaming")
    dirs = config_module._config_dirs()
    assert Path.cwd() in dirs
    assert Path(r"C:\Users\me\AppData\Roaming") / "keyvox" in dirs


def test_config_dirs_macos(monkeypatch):
    monkeypatch.setattr(config_module.os, "name", "posix", raising=False)
    monkeypatch.setattr(config_module.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(config_module, "Path", _FakePosixPath)
    dirs = config_module._config_dirs()
    assert _FakePosixPath("/work") in dirs
    assert _FakePosixPath("/home/tester/Library/Application Support/keyvox") in dirs


def test_get_platform_config_dir_windows_with_appdata(monkeypatch):
    monkeypatch.setattr(keyvox.config.os, "name", "nt")
    monkeypatch.setenv("APPDATA", "C:/Users/Test/AppData/Roaming")
    result = keyvox.config.get_platform_config_dir()
    assert result == Path("C:/Users/Test/AppData/Roaming") / "keyvox"


def test_get_platform_config_dir_windows_missing_appdata_falls_to_xdg(monkeypatch):
    monkeypatch.setattr(keyvox.config.os, "name", "nt")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    result = keyvox.config.get_platform_config_dir()
    assert str(result).endswith("keyvox")


def test_get_platform_config_dir_macos(monkeypatch):
    monkeypatch.setattr(keyvox.config.os, "name", "posix")
    monkeypatch.setattr(keyvox.config.sys, "platform", "darwin")
    monkeypatch.setattr(config_module, "Path", _FakePosixPath)
    result = keyvox.config.get_platform_config_dir()
    assert "Library/Application Support/keyvox" in str(result)


def test_config_dirs_linux(monkeypatch):
    monkeypatch.setattr(config_module.os, "name", "posix", raising=False)
    monkeypatch.setattr(config_module.sys, "platform", "linux", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    monkeypatch.setattr(config_module, "Path", _FakePosixPath)
    dirs = config_module._config_dirs()
    assert _FakePosixPath("/work") in dirs
    assert _FakePosixPath("/tmp/xdg/keyvox") in dirs
