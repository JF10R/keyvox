"""Tests for runtime config hot-reload helpers."""
import os
import tomllib
from pathlib import Path

import pytest

from keyvox.config import load_config
from keyvox.config_reload import FileReloader


def _bump_mtime(path: Path) -> None:
    """Force an mtime change for reliable polling tests."""
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


def test_file_reloader_prime_skips_unchanged_file(tmp_path):
    """After prime(), unchanged file should not trigger a load."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("a", encoding="utf-8")
    calls = []

    def loader(path: Path) -> str:
        calls.append(path)
        return path.read_text(encoding="utf-8")

    reloader = FileReloader(lambda: cfg, loader, min_interval_s=0.0)
    reloader.prime()

    assert reloader.poll() is None
    assert calls == []


def test_file_reloader_loads_when_file_changes(tmp_path):
    """Polling should return new content when mtime changes."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("v1", encoding="utf-8")
    reloader = FileReloader(
        lambda: cfg,
        lambda path: path.read_text(encoding="utf-8"),
        min_interval_s=0.0,
    )
    reloader.prime()

    cfg.write_text("v2", encoding="utf-8")
    _bump_mtime(cfg)

    assert reloader.poll() == "v2"
    assert reloader.poll() is None


def test_load_config_raise_on_error_for_invalid_toml(tmp_path):
    """Strict load must raise on invalid TOML."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("[dictionary\nbroken = true", encoding="utf-8")

    with pytest.raises(tomllib.TOMLDecodeError):
        load_config(path=cfg, quiet=True, raise_on_error=True)


def test_load_config_explicit_path_merges_defaults(tmp_path):
    """Explicit path load should merge user config with defaults."""
    cfg = tmp_path / "config.toml"
    cfg.write_text('[dictionary]\n"cloud.md" = "CLAUDE.md"\n', encoding="utf-8")

    loaded = load_config(path=cfg, quiet=True, raise_on_error=True)

    assert loaded["dictionary"]["cloud.md"] == "CLAUDE.md"
    assert loaded["text_insertion"]["normalize_urls"] is True
