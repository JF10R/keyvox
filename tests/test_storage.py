"""Tests for storage helpers and migration safeguards."""
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
