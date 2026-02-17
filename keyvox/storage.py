"""Storage path resolution and migration helpers."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

DEFAULT_HISTORY_FILENAME = "history.sqlite3"


def _expanded_path(value: str) -> Path:
    return Path(value).expanduser()


def resolve_storage_root(config: Dict[str, Any]) -> Optional[Path]:
    raw = config.get("paths", {}).get("storage_root", "")
    if isinstance(raw, str) and raw.strip():
        return _expanded_path(raw.strip())
    return None


def _default_hf_hub_cache_path() -> Path:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        return Path(HF_HUB_CACHE).expanduser()
    except Exception:
        return Path.home() / ".cache" / "huggingface" / "hub"


def _normalize_model_cache_root(path: Path) -> Path:
    return path.parent if path.name.lower() == "hub" else path


def resolve_model_cache_root(config: Dict[str, Any]) -> Path:
    configured = config.get("paths", {}).get("model_cache", "")
    if isinstance(configured, str) and configured.strip():
        return _normalize_model_cache_root(_expanded_path(configured.strip()))

    storage_root = resolve_storage_root(config)
    if storage_root is not None:
        return storage_root / "models"

    # Keep compatibility with default Hugging Face cache behavior.
    return _default_hf_hub_cache_path().parent


def resolve_model_hub_cache_dir(config: Dict[str, Any]) -> Path:
    return resolve_model_cache_root(config) / "hub"


def resolve_history_db_path(
    config: Dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Path:
    configured = config.get("paths", {}).get("history_db", "")
    if isinstance(configured, str) and configured.strip():
        return _expanded_path(configured.strip())

    storage_root = resolve_storage_root(config)
    if storage_root is not None:
        return storage_root / "history" / DEFAULT_HISTORY_FILENAME

    if config_path is not None:
        return config_path.parent / DEFAULT_HISTORY_FILENAME
    return Path.cwd() / DEFAULT_HISTORY_FILENAME


def resolve_exports_dir(
    config: Dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Path:
    storage_root = resolve_storage_root(config)
    if storage_root is not None:
        return storage_root / "exports"
    if config_path is not None:
        return config_path.parent
    return Path.cwd()


def resolve_runtime_dir(
    config: Dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Path:
    storage_root = resolve_storage_root(config)
    if storage_root is not None:
        return storage_root / "runtime"
    if config_path is not None:
        return config_path.parent / ".runtime"
    return Path.cwd() / ".runtime"


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size

    total = 0
    for file_path in path.rglob("*"):
        if file_path.is_file():
            total += file_path.stat().st_size
    return total


def _copy_dir_with_progress(
    source: Path,
    destination: Path,
    *,
    progress_cb: Callable[[int], None],
) -> None:
    if not source.exists():
        return
    files = [path for path in source.rglob("*") if path.is_file()]
    for file_path in files:
        relative = file_path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, target)
        progress_cb(file_path.stat().st_size)


def _copy_file_with_progress(
    source: Path,
    destination: Path,
    *,
    progress_cb: Callable[[int], None],
) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    progress_cb(source.stat().st_size)


def _safe_remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        path.unlink(missing_ok=True)
        return
    shutil.rmtree(path, ignore_errors=True)


def get_effective_storage_paths(
    config: Dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Dict[str, Path]:
    storage_root = resolve_storage_root(config)
    return {
        "storage_root": storage_root if storage_root is not None else Path(""),
        "model_cache_root": resolve_model_cache_root(config),
        "model_hub_cache": resolve_model_hub_cache_dir(config),
        "history_db": resolve_history_db_path(config, config_path=config_path),
        "exports_dir": resolve_exports_dir(config, config_path=config_path),
        "runtime_dir": resolve_runtime_dir(config, config_path=config_path),
    }


def get_storage_status(
    config: Dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Dict[str, Any]:
    paths = get_effective_storage_paths(config, config_path=config_path)
    root_path = (
        paths["storage_root"]
        if str(paths["storage_root"])
        else paths["model_cache_root"]
    )
    usage = shutil.disk_usage(root_path if root_path.exists() else root_path.parent)
    sizes = {
        "models_bytes": directory_size(paths["model_cache_root"]),
        "history_bytes": directory_size(paths["history_db"]),
        "exports_bytes": directory_size(paths["exports_dir"]),
        "runtime_bytes": directory_size(paths["runtime_dir"]),
    }
    return {
        "storage_root": str(paths["storage_root"]) if str(paths["storage_root"]) else "",
        "effective_paths": {key: str(value) for key, value in paths.items() if key != "storage_root"},
        "sizes": {
            **sizes,
            "total_bytes": sum(sizes.values()),
        },
        "disk_free_bytes": usage.free,
    }


def _migration_sources(
    config: Dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Dict[str, Path]:
    storage_root = resolve_storage_root(config)
    sources: Dict[str, Path] = {}
    if storage_root is not None:
        sources["model_cache_root"] = storage_root / "models"
        sources["history_db"] = storage_root / "history" / DEFAULT_HISTORY_FILENAME
        sources["exports_dir"] = storage_root / "exports"
        sources["runtime_dir"] = storage_root / "runtime"
        return sources

    configured_model_cache = config.get("paths", {}).get("model_cache", "")
    if isinstance(configured_model_cache, str) and configured_model_cache.strip():
        sources["model_cache_root"] = _normalize_model_cache_root(
            _expanded_path(configured_model_cache.strip())
        )

    configured_history_db = config.get("paths", {}).get("history_db", "")
    if isinstance(configured_history_db, str) and configured_history_db.strip():
        sources["history_db"] = _expanded_path(configured_history_db.strip())
    elif config_path is not None:
        sources["history_db"] = config_path.parent / DEFAULT_HISTORY_FILENAME
    else:
        sources["history_db"] = Path.cwd() / DEFAULT_HISTORY_FILENAME
    return sources


def estimate_migration_bytes(
    config: Dict[str, Any],
    target_root: Path,
    *,
    config_path: Path | None = None,
) -> Dict[str, int]:
    root = target_root.expanduser()
    sources = _migration_sources(config, config_path=config_path)
    breakdown: Dict[str, int] = {}
    total = 0
    for key, source in sources.items():
        if not source.exists():
            continue
        if source.resolve().is_relative_to(root.resolve()):
            continue
        size = directory_size(source)
        breakdown[key] = size
        total += size

    usage = shutil.disk_usage(root if root.exists() else root.parent)
    return {
        "bytes_required": total,
        "disk_free_bytes": usage.free,
        "breakdown": breakdown,
    }


def migrate_storage_root(
    config: Dict[str, Any],
    target_root: Path,
    *,
    config_path: Path | None = None,
    progress_cb: Callable[[Dict[str, Any]], None] | None = None,
) -> Dict[str, Any]:
    root = target_root.expanduser()
    estimate = estimate_migration_bytes(config, root, config_path=config_path)
    bytes_required = estimate["bytes_required"]
    disk_free_bytes = estimate["disk_free_bytes"]
    if disk_free_bytes < bytes_required:
        raise RuntimeError(
            f"Insufficient space on destination drive: "
            f"required={bytes_required} bytes free={disk_free_bytes} bytes"
        )
    root.mkdir(parents=True, exist_ok=True)

    def emit(status: str, copied: int, message: str) -> None:
        if not progress_cb:
            return
        total = max(1, bytes_required)
        pct = min(100, int((copied / total) * 100))
        progress_cb(
            {
                "status": status,
                "copied_bytes": copied,
                "total_bytes": bytes_required,
                "progress_pct": pct if bytes_required > 0 else 100,
                "message": message,
            }
        )

    target_model_cache = root / "models"
    target_history_db = root / "history" / DEFAULT_HISTORY_FILENAME
    target_exports = root / "exports"
    target_runtime = root / "runtime"
    target_model_cache.mkdir(parents=True, exist_ok=True)
    target_history_db.parent.mkdir(parents=True, exist_ok=True)
    target_exports.mkdir(parents=True, exist_ok=True)
    target_runtime.mkdir(parents=True, exist_ok=True)

    sources = _migration_sources(config, config_path=config_path)
    moved: Dict[str, str] = {}
    copied = 0
    emit("copying", copied, "Preparing storage migration")

    def on_bytes(amount: int) -> None:
        nonlocal copied
        copied += amount
        emit("copying", copied, "Copying files")

    source_model_cache = sources.get("model_cache_root")
    if source_model_cache and source_model_cache.exists():
        _copy_dir_with_progress(source_model_cache, target_model_cache, progress_cb=on_bytes)
        moved["model_cache_root"] = str(source_model_cache)

    source_history_db = sources.get("history_db")
    if source_history_db and source_history_db.exists():
        _copy_file_with_progress(source_history_db, target_history_db, progress_cb=on_bytes)
        moved["history_db"] = str(source_history_db)

    source_exports = sources.get("exports_dir")
    if source_exports and source_exports.exists():
        _copy_dir_with_progress(source_exports, target_exports, progress_cb=on_bytes)
        moved["exports_dir"] = str(source_exports)

    source_runtime = sources.get("runtime_dir")
    if source_runtime and source_runtime.exists():
        _copy_dir_with_progress(source_runtime, target_runtime, progress_cb=on_bytes)
        moved["runtime_dir"] = str(source_runtime)

    emit("verifying", copied, "Verifying copied data")
    if source_history_db and source_history_db.exists():
        src_size = source_history_db.stat().st_size
        dst_size = target_history_db.stat().st_size if target_history_db.exists() else -1
        if src_size != dst_size:
            raise RuntimeError("History DB verification failed after migration")

    paths = config.setdefault("paths", {})
    paths["storage_root"] = str(root)
    paths["model_cache"] = ""
    paths["history_db"] = ""

    emit("cleanup", copied, "Cleaning up previous storage location")
    for source_key, source_str in moved.items():
        source = Path(source_str)
        if source_key == "history_db":
            _safe_remove_path(source)
        elif source_key in {"exports_dir", "runtime_dir", "model_cache_root"}:
            _safe_remove_path(source)

    emit("completed", bytes_required, "Storage migration completed")
    return {
        "storage_root": str(root),
        "bytes_required": bytes_required,
        "disk_free_bytes": disk_free_bytes,
        "moved": moved,
        "completed_at": int(time.time()),
    }
