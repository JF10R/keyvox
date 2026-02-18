"""Tests for storage helpers and migration safeguards."""
import types
from pathlib import Path

import pytest

import keyvox.storage as storage_mod


def _base_config() -> dict:
    return {
        "paths": {
            "storage_root": "",
            "model_cache": "",
            "history_db": "",
        }
    }


def test_migrate_storage_root_blocks_when_destination_has_no_space(monkeypatch, tmp_path):
    config = _base_config()
    target_root = tmp_path / "target"

    monkeypatch.setattr(
        storage_mod,
        "estimate_migration_bytes",
        lambda current_config, root, config_path=None: {
            "bytes_required": 5_000_000,
            "disk_free_bytes": 1_024,
            "breakdown": {"model_cache_root": 5_000_000},
        },
    )

    with pytest.raises(RuntimeError, match="Insufficient space on destination drive"):
        storage_mod.migrate_storage_root(config, target_root)

    assert not target_root.exists()


# ---------------------------------------------------------------------------
# resolve_storage_root
# ---------------------------------------------------------------------------

def test_resolve_storage_root_returns_none_when_empty():
    config = _base_config()
    assert storage_mod.resolve_storage_root(config) is None


def test_resolve_storage_root_returns_path():
    config = _base_config()
    config["paths"]["storage_root"] = "D:/keyvox/storage"
    result = storage_mod.resolve_storage_root(config)
    assert result == Path("D:/keyvox/storage")


def test_resolve_storage_root_strips_whitespace():
    config = _base_config()
    config["paths"]["storage_root"] = "  D:/keyvox/storage  "
    result = storage_mod.resolve_storage_root(config)
    assert result == Path("D:/keyvox/storage")


def test_resolve_storage_root_none_for_whitespace_only():
    config = _base_config()
    config["paths"]["storage_root"] = "   "
    assert storage_mod.resolve_storage_root(config) is None


# ---------------------------------------------------------------------------
# resolve_model_cache_root
# ---------------------------------------------------------------------------

def test_resolve_model_cache_root_uses_explicit_config():
    config = _base_config()
    config["paths"]["model_cache"] = "D:/models/cache"
    result = storage_mod.resolve_model_cache_root(config)
    assert result == Path("D:/models/cache")


def test_resolve_model_cache_root_normalizes_hub_suffix():
    # path ending in /hub should strip the suffix so models dir is the root
    config = _base_config()
    config["paths"]["model_cache"] = "D:/models/hub"
    result = storage_mod.resolve_model_cache_root(config)
    assert result == Path("D:/models")


def test_resolve_model_cache_root_falls_back_to_storage_root():
    config = _base_config()
    config["paths"]["storage_root"] = "D:/keyvox"
    result = storage_mod.resolve_model_cache_root(config)
    assert result == Path("D:/keyvox") / "models"


# ---------------------------------------------------------------------------
# resolve_history_db_path
# ---------------------------------------------------------------------------

def test_resolve_history_db_path_uses_explicit_config():
    config = _base_config()
    config["paths"]["history_db"] = "D:/data/history.sqlite3"
    result = storage_mod.resolve_history_db_path(config)
    assert result == Path("D:/data/history.sqlite3")


def test_resolve_history_db_path_uses_storage_root():
    config = _base_config()
    config["paths"]["storage_root"] = "D:/keyvox"
    result = storage_mod.resolve_history_db_path(config)
    assert result == Path("D:/keyvox") / "history" / "history.sqlite3"


def test_resolve_history_db_path_uses_config_path(tmp_path):
    config = _base_config()
    config_path = tmp_path / "config.toml"
    result = storage_mod.resolve_history_db_path(config, config_path=config_path)
    assert result == tmp_path / "history.sqlite3"


def test_resolve_history_db_path_falls_back_to_cwd():
    config = _base_config()
    result = storage_mod.resolve_history_db_path(config, config_path=None)
    assert result == Path.cwd() / "history.sqlite3"


# ---------------------------------------------------------------------------
# directory_size
# ---------------------------------------------------------------------------

def test_directory_size_returns_zero_for_missing_path(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert storage_mod.directory_size(missing) == 0


def test_directory_size_sums_files_recursively(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"x" * 50)
    assert storage_mod.directory_size(tmp_path) == 150


def test_directory_size_handles_single_file(tmp_path):
    f = tmp_path / "file.bin"
    f.write_bytes(b"hello")
    assert storage_mod.directory_size(f) == 5


# ---------------------------------------------------------------------------
# get_effective_storage_paths
# ---------------------------------------------------------------------------

def test_get_effective_storage_paths_returns_all_keys():
    config = _base_config()
    paths = storage_mod.get_effective_storage_paths(config)
    expected_keys = {
        "storage_root",
        "model_cache_root",
        "model_hub_cache",
        "history_db",
        "exports_dir",
        "runtime_dir",
    }
    assert set(paths.keys()) == expected_keys


def test_get_effective_storage_paths_storage_root_controls_all(tmp_path):
    config = _base_config()
    config["paths"]["storage_root"] = str(tmp_path)
    paths = storage_mod.get_effective_storage_paths(config)
    assert paths["model_cache_root"] == tmp_path / "models"
    assert paths["history_db"] == tmp_path / "history" / "history.sqlite3"
    assert paths["exports_dir"] == tmp_path / "exports"
    assert paths["runtime_dir"] == tmp_path / "runtime"


# ---------------------------------------------------------------------------
# estimate_migration_bytes
# ---------------------------------------------------------------------------

def _fake_disk_usage(path):
    return types.SimpleNamespace(free=10_000_000, total=10_000_000, used=0)


def test_estimate_migration_bytes_excludes_already_at_target(tmp_path, monkeypatch):
    # Source already inside target root → bytes_required == 0
    target = tmp_path / "storage"
    target.mkdir()
    model_dir = target / "models"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"x" * 1000)

    config = _base_config()
    config["paths"]["storage_root"] = str(target)

    monkeypatch.setattr(storage_mod.shutil, "disk_usage", _fake_disk_usage)

    result = storage_mod.estimate_migration_bytes(config, target)
    assert result["bytes_required"] == 0


def test_estimate_migration_bytes_counts_external_sources(tmp_path, monkeypatch):
    # External model dir with 1000B → bytes_required == 1000
    external = tmp_path / "external_models"
    external.mkdir()
    (external / "model.bin").write_bytes(b"x" * 1000)

    target = tmp_path / "new_storage"

    config = _base_config()
    config["paths"]["model_cache"] = str(external)

    monkeypatch.setattr(storage_mod.shutil, "disk_usage", _fake_disk_usage)

    result = storage_mod.estimate_migration_bytes(config, target)
    assert result["bytes_required"] == 1000


# ---------------------------------------------------------------------------
# migrate_storage_root
# ---------------------------------------------------------------------------

def _make_source_with_model_and_db(source: Path) -> None:
    """Create a minimal source storage tree for migration tests."""
    source.mkdir(parents=True, exist_ok=True)
    model_dir = source / "models"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"model_data")
    history_dir = source / "history"
    history_dir.mkdir()
    (history_dir / "history.sqlite3").write_bytes(b"db_data_here")


def test_migrate_storage_root_copies_files_to_target(tmp_path, monkeypatch):
    source = tmp_path / "source_storage"
    _make_source_with_model_and_db(source)

    config = _base_config()
    config["paths"]["storage_root"] = str(source)
    target = tmp_path / "target_storage"

    monkeypatch.setattr(storage_mod.shutil, "disk_usage", _fake_disk_usage)

    storage_mod.migrate_storage_root(config, target)

    assert (target / "models" / "model.bin").exists()
    assert (target / "history" / "history.sqlite3").exists()


def test_migrate_storage_root_emits_progress_events(tmp_path, monkeypatch):
    source = tmp_path / "source"
    _make_source_with_model_and_db(source)

    config = _base_config()
    config["paths"]["storage_root"] = str(source)
    target = tmp_path / "target"

    monkeypatch.setattr(storage_mod.shutil, "disk_usage", _fake_disk_usage)

    events = []
    storage_mod.migrate_storage_root(config, target, progress_cb=events.append)

    statuses = [e["status"] for e in events]
    assert "copying" in statuses
    assert "completed" in statuses


def test_migrate_storage_root_updates_config_after_copy(tmp_path, monkeypatch):
    source = tmp_path / "source"
    _make_source_with_model_and_db(source)

    config = _base_config()
    config["paths"]["storage_root"] = str(source)
    config["paths"]["model_cache"] = "D:/old/models"
    config["paths"]["history_db"] = "D:/old/history.sqlite3"
    target = tmp_path / "target"

    monkeypatch.setattr(storage_mod.shutil, "disk_usage", _fake_disk_usage)

    storage_mod.migrate_storage_root(config, target)

    assert config["paths"]["storage_root"] == str(target)
    assert config["paths"]["model_cache"] == ""
    assert config["paths"]["history_db"] == ""


def test_migrate_storage_root_cleans_up_source_paths(tmp_path, monkeypatch):
    source = tmp_path / "source"
    _make_source_with_model_and_db(source)

    config = _base_config()
    config["paths"]["storage_root"] = str(source)
    target = tmp_path / "target"

    monkeypatch.setattr(storage_mod.shutil, "disk_usage", _fake_disk_usage)

    storage_mod.migrate_storage_root(config, target)

    # Source model dir and history file should be removed after migration
    assert not (source / "models").exists()
    assert not (source / "history" / "history.sqlite3").exists()


def test_migrate_storage_root_raises_on_history_db_size_mismatch(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    history_dir = source / "history"
    history_dir.mkdir()
    history_file = history_dir / "history.sqlite3"
    history_file.write_bytes(b"original_db_data")

    config = _base_config()
    config["paths"]["storage_root"] = str(source)
    target = tmp_path / "target"

    monkeypatch.setattr(storage_mod.shutil, "disk_usage", _fake_disk_usage)

    orig_copy2 = storage_mod.shutil.copy2

    def corrupting_copy2(src, dst):
        orig_copy2(src, dst)
        # Corrupt the destination to produce a size mismatch
        Path(dst).write_bytes(b"corrupted")

    monkeypatch.setattr(storage_mod.shutil, "copy2", corrupting_copy2)

    with pytest.raises(RuntimeError, match="History DB verification failed"):
        storage_mod.migrate_storage_root(config, target)
