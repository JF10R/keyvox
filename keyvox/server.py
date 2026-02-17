"""WebSocket server exposing the Keyvox engine over ws://localhost:<port>."""
from __future__ import annotations

import asyncio
import json
import platform
import shutil
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .backends import create_transcriber
from .config import get_config_path, save_config
from .dictionary import DictionaryManager
from .history import HistoryStore
from .hotkey import HotkeyManager
from .pipeline import TranscriptionPipeline
from .recorder import AudioRecorder
from .storage import (
    estimate_migration_bytes,
    get_effective_storage_paths,
    get_storage_status,
    migrate_storage_root,
    resolve_exports_dir,
    resolve_model_cache_root,
    resolve_model_hub_cache_dir,
)
from .text_insertion import TextInserter

DEFAULT_PORT = 9876
MAX_PORT_ATTEMPTS = 10
PROTOCOL_VERSION = "1.0.0"
DEFAULT_HISTORY_LIMIT = 100

BACKEND_CATALOG = {
    "auto": {
        "label": "Auto",
        "requires": [],
    },
    "faster-whisper": {
        "label": "Faster Whisper",
        "requires": ["faster-whisper", "cuda_optional"],
    },
    "qwen-asr": {
        "label": "Qwen ASR",
        "requires": ["qwen-asr"],
    },
    "qwen-asr-vllm": {
        "label": "Qwen ASR + vLLM",
        "requires": ["qwen-asr", "vllm", "linux"],
    },
}

MODEL_PRESETS = {
    "auto": [
        "large-v3-turbo",
        "Qwen/Qwen3-ASR-1.7B",
    ],
    "faster-whisper": [
        "tiny",
        "base",
        "small",
        "medium",
        "large-v3",
        "large-v3-turbo",
    ],
    "qwen-asr": [
        "Qwen/Qwen3-ASR-1.7B",
    ],
    "qwen-asr-vllm": [
        "Qwen/Qwen3-ASR-1.7B",
    ],
}

MODEL_DEVICE_OPTIONS = ["auto", "cpu", "cuda"]
MODEL_COMPUTE_TYPES = {
    "auto": ["auto", "float16", "float32", "bfloat16", "int8"],
    "faster-whisper": [
        "default",
        "int8",
        "int8_float16",
        "int8_float32",
        "float16",
        "float32",
    ],
    "qwen-asr": ["auto", "bfloat16", "float16", "float32"],
    "qwen-asr-vllm": ["auto", "bfloat16", "float16", "float32"],
}


class KeyvoxServer:
    """WebSocket server wrapping the Keyvox engine pipeline."""

    def __init__(self, config: Dict[str, Any], port: int = DEFAULT_PORT):
        self.config = config
        self.port = port
        self._client = None  # Single connected client
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._pipeline: Optional[TranscriptionPipeline] = None
        self._hotkey_manager: Optional[HotkeyManager] = None
        self._hotkey_thread: Optional[threading.Thread] = None
        self._server = None
        self._recording_started_at: Optional[float] = None
        self._download_lock = threading.Lock()
        self._active_model_download: Optional[tuple[str, str]] = None
        self._storage_lock = threading.Lock()
        self._active_storage_target: Optional[str] = None
        self._model_size_cache: Dict[str, list[tuple[str, int]]] = {}

        from .hardware import detect_hardware, recommend_model_config

        self._hw_info = detect_hardware()
        self._recommendation = recommend_model_config(self._hw_info)
        if self._hw_info["gpu_available"]:
            print(f"[OK] GPU detected: {self._hw_info['gpu_name']} ({self._hw_info['gpu_vram_gb']:.1f} GB)")
        else:
            print(f"[INFO] {self._hw_info['gpu_name']}")

        # Initialize engine components.
        self._transcriber = create_transcriber(config)
        self._recorder = AudioRecorder(
            sample_rate=config["audio"]["sample_rate"],
            input_device=config["audio"]["input_device"],
        )
        self._dictionary = DictionaryManager.load_from_config(config)
        self._text_inserter = TextInserter(
            config=config.get("text_insertion", {}),
            dictionary_corrections=self._dictionary.corrections,
        )
        self._history_store = HistoryStore.from_config(config)

    def _protocol_base(self) -> Dict[str, Any]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _make_event(self, event_type: str, **payload: Any) -> Dict[str, Any]:
        event = {"type": event_type}
        event.update(self._protocol_base())
        event.update(payload)
        return event

    def _make_response(
        self,
        *,
        request_id: str | int | None,
        response_type: str,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            **self._protocol_base(),
            "type": "response",
            "request_id": request_id,
            "response_type": response_type,
            "ok": True,
            "result": result,
        }

    def _make_error(
        self,
        *,
        request_id: str | int | None,
        code: str,
        message: str,
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        payload = {
            **self._protocol_base(),
            "type": "response",
            "request_id": request_id,
            "response_type": "error",
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        }
        if details:
            payload["error"]["details"] = details
        return payload

    @staticmethod
    def _coerce_request_id(value: Any) -> str | int | None:
        if value is None:
            return None
        if isinstance(value, (str, int)):
            return value
        raise ValueError("request_id must be a string or integer")

    async def _send_json(self, websocket, payload: Dict[str, Any]) -> None:
        await websocket.send(json.dumps(payload))

    async def _send_response(
        self,
        websocket,
        *,
        request_id: str | int | None,
        response_type: str,
        result: Dict[str, Any],
    ) -> None:
        await self._send_json(
            websocket,
            self._make_response(
                request_id=request_id,
                response_type=response_type,
                result=result,
            ),
        )

    async def _send_error(
        self,
        websocket,
        *,
        request_id: str | int | None,
        code: str,
        message: str,
        details: Dict[str, Any] | None = None,
    ) -> None:
        await self._send_json(
            websocket,
            self._make_error(
                request_id=request_id,
                code=code,
                message=message,
                details=details,
            ),
        )

    def _broadcast(self, message: Dict[str, Any]) -> None:
        """Send JSON message to connected client (thread-safe)."""
        if self._client is None or self._loop is None or self._loop.is_closed():
            return
        if "protocol_version" not in message:
            message = {**self._protocol_base(), **message}
        data = json.dumps(message)
        try:
            asyncio.run_coroutine_threadsafe(self._safe_send(data), self._loop)
        except RuntimeError:
            # Loop is shutting down.
            return

    async def _safe_send(self, data: str) -> None:
        """Send data to client, ignore errors from disconnected client."""
        if self._client is None:
            return
        try:
            await self._client.send(data)
        except Exception:
            self._client = None

    def _persist_config(self) -> bool:
        """Save current config to config.toml when possible."""
        config_path = get_config_path()
        if config_path is None:
            print("[WARN] No config file found, changes are in-memory only")
            return False
        try:
            save_config(config_path, self.config)
            return True
        except Exception as e:
            print(f"[WARN] Failed to save config: {e}")
            return False

    def _reload_dictionary_runtime(self) -> None:
        # Update server-side references (used by get_dictionary command).
        self._dictionary = DictionaryManager.load_from_config(self.config)
        self._text_inserter = TextInserter(
            config=self.config.get("text_insertion", {}),
            dictionary_corrections=self._dictionary.corrections,
        )
        # Propagate to the pipeline worker thread.
        if self._pipeline is not None:
            self._pipeline.reload_config(self.config)

    def _default_export_path(self, export_format: str) -> Path:
        base_dir = resolve_exports_dir(self.config, config_path=get_config_path())
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return base_dir / f"keyvox-history-{timestamp}.{export_format}"

    def _request_shutdown(self) -> None:
        """Schedule graceful shutdown."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

    @staticmethod
    def _module_available(module_name: str) -> bool:
        try:
            __import__(module_name)
            return True
        except Exception:
            return False

    def _backend_available(self, backend_id: str) -> bool:
        if backend_id == "auto":
            return True
        if backend_id == "faster-whisper":
            return self._module_available("faster_whisper")
        if backend_id == "qwen-asr":
            return self._module_available("qwen_asr")
        if backend_id == "qwen-asr-vllm":
            if platform.system() != "Linux":
                return False
            return self._module_available("qwen_asr") and self._module_available("vllm")
        return False

    def _build_capabilities(self) -> Dict[str, Any]:
        backends = []
        for backend_id, meta in BACKEND_CATALOG.items():
            backends.append(
                {
                    "id": backend_id,
                    "label": meta["label"],
                    "available": self._backend_available(backend_id),
                    "requires": list(meta["requires"]),
                }
            )

        model_download_status = []
        model_requirements = []
        for backend_id, models in MODEL_PRESETS.items():
            for model_name in models:
                model_download_status.append(
                    {
                        "backend": backend_id,
                        "name": model_name,
                        "downloaded": self._is_model_downloaded(backend_id, model_name),
                    }
                )
                if backend_id != "auto":
                    model_requirements.append(self._model_requirement(backend_id, model_name))

        active_download = self._get_active_download()
        storage_status = get_storage_status(self.config, config_path=get_config_path())
        return {
            "backends": backends,
            "model_presets": MODEL_PRESETS,
            "model_devices": MODEL_DEVICE_OPTIONS,
            "compute_types": MODEL_COMPUTE_TYPES,
            "model_download_status": model_download_status,
            "model_requirements": model_requirements,
            "active_model_download": (
                {
                    "backend": active_download[0],
                    "name": active_download[1],
                }
                if active_download
                else None
            ),
            "storage": {
                "storage_root": storage_status["storage_root"],
                "effective_paths": storage_status["effective_paths"],
            },
            "restart_policy": {
                "hotkey": True,
                "model": True,
                "audio": True,
                "dictionary": False,
                "text_insertion": False,
            },
            "hardware": self._hw_info,
            "recommendation": self._recommendation,
        }

    def _model_cache_dir(self) -> str:
        return str(resolve_model_cache_root(self.config))

    def _model_hub_cache_dir(self) -> str:
        return str(resolve_model_hub_cache_dir(self.config))

    @staticmethod
    def _resolve_repo_id(backend: str, model_name: str) -> Optional[str]:
        if backend in {"qwen-asr", "qwen-asr-vllm"}:
            return model_name if "/" in model_name else None
        if backend == "faster-whisper":
            if "/" in model_name:
                return model_name
            return f"Systran/faster-whisper-{model_name}"
        return None

    def _is_model_downloaded(self, backend: str, model_name: str) -> Optional[bool]:
        repo_id = self._resolve_repo_id(backend, model_name)
        if not repo_id:
            return None

        try:
            from huggingface_hub import snapshot_download
            from huggingface_hub.utils import LocalEntryNotFoundError
        except Exception:
            return None

        kwargs: Dict[str, Any] = {
            "repo_id": repo_id,
            "local_files_only": True,
        }
        cache_dir = self._model_hub_cache_dir()
        kwargs["cache_dir"] = cache_dir

        try:
            snapshot_download(**kwargs)
            return True
        except LocalEntryNotFoundError:
            return False
        except Exception:
            return None

    def _model_file_sizes(self, repo_id: str) -> list[tuple[str, int]]:
        if repo_id in self._model_size_cache:
            return self._model_size_cache[repo_id]

        try:
            from huggingface_hub import HfApi

            info = HfApi().model_info(repo_id, files_metadata=True)
        except Exception:
            self._model_size_cache[repo_id] = []
            return []

        files: list[tuple[str, int]] = []
        for sibling in info.siblings:
            size = getattr(sibling, "size", None)
            name = getattr(sibling, "rfilename", None)
            if isinstance(name, str) and isinstance(size, int) and size > 0:
                files.append((name, size))
        self._model_size_cache[repo_id] = files
        return files

    def _model_requirement(self, backend: str, model_name: str) -> Dict[str, Any]:
        repo_id = self._resolve_repo_id(backend, model_name)
        if not repo_id:
            return {
                "backend": backend,
                "name": model_name,
                "estimated_total_bytes": None,
                "already_present_bytes": None,
                "remaining_bytes": None,
                "disk_free_bytes": None,
                "enough_space": None,
            }

        file_sizes = self._model_file_sizes(repo_id)
        if not file_sizes:
            return {
                "backend": backend,
                "name": model_name,
                "estimated_total_bytes": None,
                "already_present_bytes": None,
                "remaining_bytes": None,
                "disk_free_bytes": None,
                "enough_space": None,
            }

        total_bytes = sum(size for _, size in file_sizes)
        hub_dir = self._model_hub_cache_dir()
        present_bytes = 0
        try:
            from huggingface_hub import hf_hub_download

            for file_name, file_size in file_sizes:
                try:
                    hf_hub_download(
                        repo_id=repo_id,
                        filename=file_name,
                        local_files_only=True,
                        cache_dir=hub_dir,
                    )
                    present_bytes += file_size
                except Exception:
                    continue
        except Exception:
            present_bytes = total_bytes if self._is_model_downloaded(backend, model_name) else 0

        remaining = max(0, total_bytes - present_bytes)
        disk_path = Path(hub_dir)
        usage = shutil.disk_usage(disk_path if disk_path.exists() else disk_path.parent)
        return {
            "backend": backend,
            "name": model_name,
            "estimated_total_bytes": total_bytes,
            "already_present_bytes": present_bytes,
            "remaining_bytes": remaining,
            "disk_free_bytes": usage.free,
            "enough_space": usage.free >= remaining,
        }

    def _get_active_download(self) -> Optional[tuple[str, str]]:
        with self._download_lock:
            return self._active_model_download

    def _reserve_download(self, backend: str, model_name: str) -> bool:
        with self._download_lock:
            if self._active_model_download is not None:
                return False
            self._active_model_download = (backend, model_name)
            return True

    def _release_download(self) -> None:
        with self._download_lock:
            self._active_model_download = None

    def _get_active_storage_target(self) -> Optional[str]:
        with self._storage_lock:
            return self._active_storage_target

    def _reserve_storage_target(self, target_root: str) -> bool:
        with self._storage_lock:
            if self._active_storage_target is not None:
                return False
            self._active_storage_target = target_root
            return True

    def _release_storage_target(self) -> None:
        with self._storage_lock:
            self._active_storage_target = None

    def _broadcast_storage_migration(
        self,
        *,
        status: str,
        target_root: str,
        message: str,
        progress_pct: int,
        total_bytes: int | None = None,
        copied_bytes: int | None = None,
    ) -> None:
        self._broadcast(
            self._make_event(
                "storage_migration",
                status=status,
                target_root=target_root,
                message=message,
                progress_pct=progress_pct,
                total_bytes=total_bytes,
                copied_bytes=copied_bytes,
            )
        )

    def _broadcast_model_download(
        self,
        *,
        download_id: str,
        status: str,
        backend: str,
        name: str,
        message: str,
        progress_pct: int,
        bytes_total: int | None = None,
        bytes_completed: int | None = None,
        bytes_remaining: int | None = None,
        repo_id: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "download_id": download_id,
            "status": status,
            "backend": backend,
            "name": name,
            "message": message,
            "progress_pct": progress_pct,
            "bytes_total": bytes_total,
            "bytes_completed": bytes_completed,
            "bytes_remaining": bytes_remaining,
        }
        if repo_id:
            payload["repo_id"] = repo_id
        # Keep legacy event for existing consumers.
        self._broadcast(self._make_event("model_download", **payload))
        self._broadcast(self._make_event("model_download_progress", **payload))

    def _download_model_snapshot(
        self,
        *,
        download_id: str,
        backend: str,
        model_name: str,
    ) -> tuple[str, int, int]:
        repo_id = self._resolve_repo_id(backend, model_name)
        if not repo_id:
            raise ValueError(
                f"Cannot resolve downloadable repository for backend '{backend}' model '{model_name}'"
            )

        try:
            from huggingface_hub import hf_hub_download, snapshot_download
        except Exception as exc:
            raise RuntimeError(f"huggingface_hub is required for model download: {exc}") from exc

        hub_cache_dir = self._model_hub_cache_dir()
        file_sizes = self._model_file_sizes(repo_id)

        if not file_sizes:
            # Fallback path when metadata is unavailable.
            self._broadcast_model_download(
                download_id=download_id,
                status="resolving",
                backend=backend,
                name=model_name,
                message="Resolving model files...",
                progress_pct=15,
                repo_id=repo_id,
            )
            snapshot_download(repo_id=repo_id, cache_dir=hub_cache_dir)
            self._broadcast_model_download(
                download_id=download_id,
                status="finalizing",
                backend=backend,
                name=model_name,
                message="Finalizing model cache...",
                progress_pct=90,
                repo_id=repo_id,
            )
            self._broadcast_model_download(
                download_id=download_id,
                status="completed",
                backend=backend,
                name=model_name,
                message="Model downloaded.",
                progress_pct=100,
                repo_id=repo_id,
            )
            return repo_id, 0, 0

        total_bytes = sum(size for _, size in file_sizes)
        completed_bytes = 0
        missing_files: list[tuple[str, int]] = []
        for file_name, file_size in file_sizes:
            try:
                hf_hub_download(
                    repo_id=repo_id,
                    filename=file_name,
                    local_files_only=True,
                    cache_dir=hub_cache_dir,
                )
                completed_bytes += file_size
            except Exception:
                missing_files.append((file_name, file_size))

        self._broadcast_model_download(
            download_id=download_id,
            status="resolving",
            backend=backend,
            name=model_name,
            message="Resolved model files.",
            progress_pct=int((completed_bytes / total_bytes) * 100),
            bytes_total=total_bytes,
            bytes_completed=completed_bytes,
            bytes_remaining=max(0, total_bytes - completed_bytes),
            repo_id=repo_id,
        )

        for file_name, file_size in missing_files:
            hf_hub_download(
                repo_id=repo_id,
                filename=file_name,
                cache_dir=hub_cache_dir,
            )
            completed_bytes += file_size
            self._broadcast_model_download(
                download_id=download_id,
                status="downloading",
                backend=backend,
                name=model_name,
                message=f"Downloaded {file_name}",
                progress_pct=int((completed_bytes / total_bytes) * 100),
                bytes_total=total_bytes,
                bytes_completed=completed_bytes,
                bytes_remaining=max(0, total_bytes - completed_bytes),
                repo_id=repo_id,
            )

        self._broadcast_model_download(
            download_id=download_id,
            status="finalizing",
            backend=backend,
            name=model_name,
            message="Finalizing model cache...",
            progress_pct=99,
            bytes_total=total_bytes,
            bytes_completed=completed_bytes,
            bytes_remaining=max(0, total_bytes - completed_bytes),
            repo_id=repo_id,
        )
        self._broadcast_model_download(
            download_id=download_id,
            status="completed",
            backend=backend,
            name=model_name,
            message="Model downloaded.",
            progress_pct=100,
            bytes_total=total_bytes,
            bytes_completed=total_bytes,
            bytes_remaining=0,
            repo_id=repo_id,
        )
        return repo_id, total_bytes, total_bytes

    def _run_model_download_worker(self, download_id: str, backend: str, model_name: str) -> None:
        repo_id = self._resolve_repo_id(backend, model_name)
        try:
            self._broadcast_model_download(
                download_id=download_id,
                status="starting",
                backend=backend,
                name=model_name,
                message="Starting model download.",
                progress_pct=1,
                repo_id=repo_id,
            )
            resolved_repo, _, _ = self._download_model_snapshot(
                download_id=download_id,
                backend=backend,
                model_name=model_name,
            )
            # Keep mypy/pylint quiet on unused variable.
            _ = resolved_repo
        except Exception as exc:
            self._broadcast_model_download(
                download_id=download_id,
                status="failed",
                backend=backend,
                name=model_name,
                message=f"Model download failed: {exc}",
                progress_pct=100,
                repo_id=repo_id,
            )
        finally:
            self._release_download()

    @staticmethod
    def _list_audio_input_devices() -> list[Dict[str, Any]]:
        import sounddevice as sd

        devices = sd.query_devices()
        default_input = None
        try:
            default_device = sd.default.device
            if isinstance(default_device, (list, tuple)) and len(default_device) >= 1:
                default_input = int(default_device[0])
            elif isinstance(default_device, int):
                default_input = int(default_device)
        except Exception:
            default_input = None

        entries: list[Dict[str, Any]] = []
        for idx, device in enumerate(devices):
            max_input_channels = int(device.get("max_input_channels", 0))
            if max_input_channels <= 0:
                continue
            entries.append(
                {
                    "id": idx,
                    "name": str(device.get("name", f"Device {idx}")),
                    "max_input_channels": max_input_channels,
                    "default_samplerate": int(device.get("default_samplerate", 0)),
                    "is_default_input": idx == default_input,
                }
            )
        return entries

    def _validate_model_payload(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        errors: list[Dict[str, str]] = []
        warnings: list[Dict[str, str]] = []

        backend_raw = msg.get("backend")
        name_raw = msg.get("name")
        device_raw = msg.get("device")
        compute_type_raw = msg.get("compute_type")

        fields = {
            "backend": backend_raw,
            "name": name_raw,
            "device": device_raw,
            "compute_type": compute_type_raw,
        }
        normalized: Dict[str, str] = {}
        for field, value in fields.items():
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    {
                        "code": "missing_field",
                        "field": field,
                        "message": f"'{field}' must be a non-empty string",
                    }
                )
                continue
            normalized[field] = value.strip()

        if errors:
            return {
                "valid": False,
                "normalized": normalized,
                "errors": errors,
                "warnings": warnings,
            }

        backend = normalized["backend"].lower()
        device = normalized["device"].lower()
        compute_type = normalized["compute_type"].lower()
        model_name = normalized["name"]

        normalized["backend"] = backend
        normalized["device"] = device
        normalized["compute_type"] = compute_type
        normalized["name"] = model_name

        if backend not in BACKEND_CATALOG:
            errors.append(
                {
                    "code": "invalid_value",
                    "field": "backend",
                    "message": f"Unknown backend '{backend}'",
                }
            )

        if device not in MODEL_DEVICE_OPTIONS:
            errors.append(
                {
                    "code": "invalid_value",
                    "field": "device",
                    "message": f"Unsupported device '{device}'",
                }
            )

        backend_compute_types = MODEL_COMPUTE_TYPES.get(backend, MODEL_COMPUTE_TYPES["auto"])
        if compute_type not in backend_compute_types:
            errors.append(
                {
                    "code": "invalid_value",
                    "field": "compute_type",
                    "message": (
                        f"Unsupported compute_type '{compute_type}' for backend '{backend}'"
                    ),
                }
            )

        if backend == "qwen-asr-vllm" and platform.system() != "Linux":
            errors.append(
                {
                    "code": "unsupported_platform",
                    "field": "backend",
                    "message": "qwen-asr-vllm is supported on Linux only",
                }
            )

        if device == "cuda" and not self._hw_info["gpu_available"]:
            warnings.append(
                {
                    "code": "cuda_unavailable",
                    "field": "device",
                    "message": "CUDA device selected but CUDA does not appear available",
                }
            )

        return {
            "valid": len(errors) == 0,
            "normalized": normalized,
            "errors": errors,
            "warnings": warnings,
        }

    # --- Engine event handlers -> WebSocket broadcast ---

    def _on_recording_started(self) -> None:
        self._recording_started_at = time.monotonic()
        self._broadcast(self._make_event("state", state="recording"))

    def _on_recording_stopped(self) -> None:
        # Processing state is emitted by transcription_started.
        return

    def _on_transcription_started(self) -> None:
        self._broadcast(self._make_event("state", state="processing"))

    def _on_transcription_completed(self, text: str) -> None:
        duration_ms = None
        if self._recording_started_at is not None:
            duration_ms = int((time.monotonic() - self._recording_started_at) * 1000)
        self._recording_started_at = None

        entry = None
        if text.strip():
            entry = self._history_store.add_entry(
                text=text,
                duration_ms=duration_ms,
                backend=self.config["model"]["backend"],
                model=self.config["model"]["name"],
            )

        self._broadcast(
            self._make_event(
                "transcription",
                text=text,
                duration_ms=duration_ms,
                entry=entry,
            )
        )
        if entry is not None:
            self._broadcast(self._make_event("history_appended", entry=entry))
        self._broadcast(self._make_event("state", state="idle"))

    def _on_error(self, error_msg: str) -> None:
        self._broadcast(self._make_event("error", message=error_msg))
        self._broadcast(self._make_event("state", state="idle"))

    # --- WebSocket command handlers ---

    async def _cmd_get_config(self, websocket, request_id: str | int | None) -> None:
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="config",
            result={
                "hotkey": self.config["hotkey"]["push_to_talk"],
                "backend": self.config["model"]["backend"],
                "model": self.config["model"]["name"],
            },
        )

    async def _cmd_get_full_config(self, websocket, request_id: str | int | None) -> None:
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="full_config",
            result={"config": self.config},
        )

    async def _cmd_get_server_info(self, websocket, request_id: str | int | None) -> None:
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="server_info",
            result={
                "name": "keyvox",
                "protocol_version": PROTOCOL_VERSION,
                "port": self.port,
                "single_client": True,
                "history_db_path": str(self._history_store.db_path),
            },
        )

    async def _cmd_ping(self, websocket, request_id: str | int | None) -> None:
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="pong",
            result={"pong": True},
        )

    async def _cmd_get_capabilities(self, websocket, request_id: str | int | None) -> None:
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="capabilities",
            result=self._build_capabilities(),
        )

    async def _cmd_list_audio_devices(self, websocket, request_id: str | int | None) -> None:
        try:
            devices = self._list_audio_input_devices()
        except Exception as exc:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="internal_error",
                message=f"Failed to enumerate audio devices: {exc}",
            )
            return

        audio = self.config.get("audio", {})
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="audio_devices",
            result={
                "devices": devices,
                "current_input_device": audio.get("input_device", "default"),
                "current_sample_rate": audio.get("sample_rate"),
            },
        )

    async def _cmd_validate_model_config(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        result = self._validate_model_payload(msg)
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="model_validation",
            result=result,
        )

    async def _cmd_get_storage_status(self, websocket, request_id: str | int | None) -> None:
        status = get_storage_status(self.config, config_path=get_config_path())
        estimate_target = (
            Path(status["storage_root"])
            if status["storage_root"]
            else Path(status["effective_paths"]["model_cache_root"])
        )
        estimate = estimate_migration_bytes(
            self.config,
            estimate_target,
            config_path=get_config_path(),
        )
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="storage_status",
            result={
                **status,
                "migration_estimate": estimate,
                "active_target": self._get_active_storage_target(),
            },
        )

    def _run_storage_migration_worker(self, target_root: str) -> None:
        try:
            self._broadcast_storage_migration(
                status="starting",
                target_root=target_root,
                message="Preparing migration",
                progress_pct=1,
            )

            def on_progress(payload: Dict[str, Any]) -> None:
                self._broadcast_storage_migration(
                    status=str(payload.get("status", "copying")),
                    target_root=target_root,
                    message=str(payload.get("message", "")),
                    progress_pct=int(payload.get("progress_pct", 0)),
                    total_bytes=int(payload.get("total_bytes", 0)),
                    copied_bytes=int(payload.get("copied_bytes", 0)),
                )

            result = migrate_storage_root(
                self.config,
                Path(target_root),
                config_path=get_config_path(),
                progress_cb=on_progress,
            )
            persisted = self._persist_config()
            self._history_store = HistoryStore.from_config(self.config)
            self._broadcast_storage_migration(
                status="completed",
                target_root=target_root,
                message="Storage migration completed",
                progress_pct=100,
                total_bytes=int(result.get("bytes_required", 0)),
                copied_bytes=int(result.get("bytes_required", 0)),
            )
            self._broadcast(
                self._make_event(
                    "storage_updated",
                    storage_root=target_root,
                    persisted=persisted,
                )
            )
        except Exception as exc:
            self._broadcast_storage_migration(
                status="failed",
                target_root=target_root,
                message=f"Storage migration failed: {exc}",
                progress_pct=100,
            )
        finally:
            self._release_storage_target()

    async def _cmd_set_storage_root(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        target_raw = msg.get("storage_root")
        if not isinstance(target_raw, str) or not target_raw.strip():
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="set_storage_root requires non-empty string 'storage_root'",
            )
            return

        target_root = Path(target_raw.strip()).expanduser()
        if not target_root.is_absolute():
            target_root = target_root.resolve()

        estimate = estimate_migration_bytes(
            self.config,
            target_root,
            config_path=get_config_path(),
        )
        if estimate["disk_free_bytes"] < estimate["bytes_required"]:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="insufficient_space",
                message=(
                    "Destination drive does not have enough free space for migration: "
                    f"required={estimate['bytes_required']} bytes, "
                    f"free={estimate['disk_free_bytes']} bytes"
                ),
                details=estimate,
            )
            return

        if self._get_active_download() is not None:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="download_in_progress",
                message="Storage migration blocked while a model download is active",
            )
            return

        if not self._reserve_storage_target(str(target_root)):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="migration_in_progress",
                message="Storage migration already in progress",
            )
            return

        worker = threading.Thread(
            target=self._run_storage_migration_worker,
            args=(str(target_root),),
            daemon=True,
        )
        worker.start()

        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="storage_migration_started",
            result={
                "started": True,
                "storage_root": str(target_root),
                "migration_estimate": estimate,
            },
        )

    async def _cmd_download_model(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        backend_raw = msg.get("backend")
        name_raw = msg.get("name")

        if not isinstance(backend_raw, str) or not backend_raw.strip():
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="download_model requires non-empty string 'backend'",
            )
            return
        if not isinstance(name_raw, str) or not name_raw.strip():
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="download_model requires non-empty string 'name'",
            )
            return

        backend = backend_raw.strip().lower()
        model_name = name_raw.strip()
        if backend == "auto":
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="download_model requires an explicit backend (not 'auto')",
            )
            return
        if backend not in BACKEND_CATALOG:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message=f"Unknown backend '{backend}'",
            )
            return

        requirement = self._model_requirement(backend, model_name)
        remaining_bytes = requirement.get("remaining_bytes")
        disk_free_bytes = requirement.get("disk_free_bytes")
        if (
            isinstance(remaining_bytes, int)
            and isinstance(disk_free_bytes, int)
            and disk_free_bytes < remaining_bytes
        ):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="insufficient_space",
                message=(
                    "Destination model cache path does not have enough free space: "
                    f"required={remaining_bytes} bytes, free={disk_free_bytes} bytes"
                ),
                details=requirement,
            )
            return

        already_downloaded = self._is_model_downloaded(backend, model_name)
        if already_downloaded is True:
            await self._send_response(
                websocket,
                request_id=request_id,
                response_type="model_download_started",
                result={
                    "started": False,
                    "already_downloaded": True,
                    "backend": backend,
                    "name": model_name,
                },
            )
            return

        if not self._reserve_download(backend, model_name):
            active = self._get_active_download()
            await self._send_error(
                websocket,
                request_id=request_id,
                code="download_in_progress",
                message=(
                    f"Model download already in progress for "
                    f"{active[0]}:{active[1]}" if active else "Model download already in progress"
                ),
            )
            return

        download_id = f"mdl-{int(time.time() * 1000)}"
        worker = threading.Thread(
            target=self._run_model_download_worker,
            args=(download_id, backend, model_name),
            daemon=True,
        )
        worker.start()

        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="model_download_started",
            result={
                "started": True,
                "already_downloaded": False,
                "backend": backend,
                "name": model_name,
                "download_id": download_id,
            },
        )

    async def _cmd_get_dictionary(self, websocket, request_id: str | int | None) -> None:
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="dictionary",
            result={"entries": self._dictionary.corrections},
        )

    async def _cmd_set_dictionary(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        key_raw = msg.get("key")
        value_raw = msg.get("value")
        key = key_raw.strip().lower() if isinstance(key_raw, str) else ""
        value = value_raw.strip() if isinstance(value_raw, str) else ""
        if not key or not value:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="set_dictionary requires non-empty string 'key' and 'value'",
            )
            return

        self.config.setdefault("dictionary", {})[key] = value
        self._reload_dictionary_runtime()
        persisted = self._persist_config()

        self._broadcast(self._make_event("dictionary_updated", key=key, value=value))
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="dictionary_updated",
            result={"key": key, "value": value, "persisted": persisted},
        )

    async def _cmd_delete_dictionary(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        key_raw = msg.get("key")
        key = key_raw.strip().lower() if isinstance(key_raw, str) else ""
        dictionary = self.config.setdefault("dictionary", {})
        if not key or key not in dictionary:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="not_found",
                message=f"Key '{key}' not found in dictionary",
            )
            return

        del dictionary[key]
        self._reload_dictionary_runtime()
        persisted = self._persist_config()

        self._broadcast(self._make_event("dictionary_deleted", key=key))
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="dictionary_deleted",
            result={"key": key, "persisted": persisted},
        )

    async def _cmd_set_config_section(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        section = msg.get("section")
        values = msg.get("values")
        if not isinstance(section, str) or not section.strip():
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="set_config_section requires string 'section'",
            )
            return
        if not isinstance(values, dict):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="set_config_section requires object 'values'",
            )
            return
        current = self.config.get(section)
        if not isinstance(current, dict):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_section",
                message=f"Config section '{section}' is not editable",
            )
            return

        current.update(values)
        persisted = self._persist_config()
        restart_required = section in {"model", "audio", "hotkey"}
        if section in {"dictionary", "text_insertion"}:
            self._reload_dictionary_runtime()

        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="config_section_updated",
            result={
                "section": section,
                "values": current,
                "persisted": persisted,
                "restart_required": restart_required,
            },
        )

    async def _cmd_set_hotkey(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        hotkey = msg.get("hotkey")
        if not isinstance(hotkey, str) or not hotkey.strip():
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="set_hotkey requires non-empty string 'hotkey'",
            )
            return
        self.config.setdefault("hotkey", {})["push_to_talk"] = hotkey.strip().lower()
        persisted = self._persist_config()
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="hotkey_updated",
            result={
                "hotkey": self.config["hotkey"]["push_to_talk"],
                "persisted": persisted,
                "restart_required": True,
            },
        )

    async def _cmd_set_model(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        model_updates = {}
        for key in ("backend", "name", "device", "compute_type"):
            value = msg.get(key)
            if value is not None:
                if not isinstance(value, str) or not value.strip():
                    await self._send_error(
                        websocket,
                        request_id=request_id,
                        code="invalid_payload",
                        message=f"set_model field '{key}' must be non-empty string",
                    )
                    return
                model_updates[key] = value.strip()

        if not model_updates:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="set_model requires at least one of backend/name/device/compute_type",
            )
            return

        self.config.setdefault("model", {}).update(model_updates)
        persisted = self._persist_config()
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="model_updated",
            result={
                "model": self.config["model"],
                "persisted": persisted,
                "restart_required": True,
            },
        )

    async def _cmd_set_audio_device(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        input_device = msg.get("input_device")
        sample_rate = msg.get("sample_rate")

        if input_device is not None and not isinstance(input_device, (str, int)):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="input_device must be string or integer",
            )
            return

        if sample_rate is not None:
            if not isinstance(sample_rate, int) or sample_rate <= 0:
                await self._send_error(
                    websocket,
                    request_id=request_id,
                    code="invalid_payload",
                    message="sample_rate must be a positive integer",
                )
                return

        if input_device is None and sample_rate is None:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="set_audio_device requires input_device and/or sample_rate",
            )
            return

        audio = self.config.setdefault("audio", {})
        if input_device is not None:
            audio["input_device"] = input_device
        if sample_rate is not None:
            audio["sample_rate"] = sample_rate

        persisted = self._persist_config()
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="audio_updated",
            result={
                "audio": self.config["audio"],
                "persisted": persisted,
                "restart_required": True,
            },
        )

    async def _cmd_get_history(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        limit = msg.get("limit", DEFAULT_HISTORY_LIMIT)
        offset = msg.get("offset", 0)
        search = msg.get("search", "")
        if not isinstance(limit, int) or limit <= 0:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="get_history 'limit' must be a positive integer",
            )
            return
        if not isinstance(offset, int) or offset < 0:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="get_history 'offset' must be a non-negative integer",
            )
            return
        if not isinstance(search, str):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="get_history 'search' must be a string",
            )
            return

        entries = self._history_store.list_entries(limit=limit, offset=offset, search=search)
        total = self._history_store.count_entries(search=search)
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="history",
            result={
                "entries": entries,
                "total": total,
                "limit": limit,
                "offset": offset,
                "search": search,
            },
        )

    async def _cmd_delete_history_item(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        entry_id = msg.get("id")
        if not isinstance(entry_id, int) or entry_id <= 0:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="delete_history_item requires positive integer 'id'",
            )
            return
        deleted = self._history_store.delete_entry(entry_id)
        if not deleted:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="not_found",
                message=f"History id '{entry_id}' was not found",
            )
            return
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="history_item_deleted",
            result={"id": entry_id},
        )

    async def _cmd_clear_history(self, websocket, request_id: str | int | None) -> None:
        removed = self._history_store.clear()
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="history_cleared",
            result={"removed": removed},
        )

    async def _cmd_export_history(
        self,
        websocket,
        request_id: str | int | None,
        msg: Dict[str, Any],
    ) -> None:
        export_format = msg.get("format", "txt")
        path_raw = msg.get("path")
        if not isinstance(export_format, str):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="export_history 'format' must be a string",
            )
            return
        export_format = export_format.strip().lower()
        if path_raw is not None and not isinstance(path_raw, str):
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="export_history 'path' must be a string",
            )
            return
        path = Path(path_raw) if isinstance(path_raw, str) and path_raw.strip() else self._default_export_path(export_format)

        if export_format == "txt":
            output_path = self._history_store.export_txt(path)
        elif export_format == "csv":
            output_path = self._history_store.export_csv(path)
        else:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="export_history format must be 'txt' or 'csv'",
            )
            return
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="history_exported",
            result={"path": str(output_path), "format": export_format},
        )

    async def _cmd_shutdown(self, websocket, request_id: str | int | None) -> None:
        await self._send_response(
            websocket,
            request_id=request_id,
            response_type="shutting_down",
            result={"shutting_down": True},
        )
        self._broadcast(self._make_event("shutting_down"))
        print("[INFO] Shutdown requested by client")
        self._request_shutdown()

    async def _handle_command(self, msg: Dict[str, Any], websocket) -> None:
        """Route incoming command to handler."""
        try:
            request_id = self._coerce_request_id(msg.get("request_id"))
        except ValueError as exc:
            await self._send_error(
                websocket,
                request_id=None,
                code="invalid_payload",
                message=str(exc),
            )
            return

        cmd = msg.get("type")
        if not isinstance(cmd, str) or not cmd.strip():
            await self._send_error(
                websocket,
                request_id=request_id,
                code="invalid_payload",
                message="Command 'type' must be a non-empty string",
            )
            return
        cmd = cmd.strip()

        if cmd == "get_config":
            await self._cmd_get_config(websocket, request_id)
        elif cmd == "get_full_config":
            await self._cmd_get_full_config(websocket, request_id)
        elif cmd in {"server_info", "get_server_info"}:
            await self._cmd_get_server_info(websocket, request_id)
        elif cmd == "ping":
            await self._cmd_ping(websocket, request_id)
        elif cmd == "get_capabilities":
            await self._cmd_get_capabilities(websocket, request_id)
        elif cmd == "get_storage_status":
            await self._cmd_get_storage_status(websocket, request_id)
        elif cmd == "set_storage_root":
            await self._cmd_set_storage_root(websocket, request_id, msg)
        elif cmd == "list_audio_devices":
            await self._cmd_list_audio_devices(websocket, request_id)
        elif cmd == "validate_model_config":
            await self._cmd_validate_model_config(websocket, request_id, msg)
        elif cmd == "download_model":
            await self._cmd_download_model(websocket, request_id, msg)
        elif cmd == "get_dictionary":
            await self._cmd_get_dictionary(websocket, request_id)
        elif cmd == "set_dictionary":
            await self._cmd_set_dictionary(websocket, request_id, msg)
        elif cmd == "delete_dictionary":
            await self._cmd_delete_dictionary(websocket, request_id, msg)
        elif cmd == "set_config_section":
            await self._cmd_set_config_section(websocket, request_id, msg)
        elif cmd == "set_hotkey":
            await self._cmd_set_hotkey(websocket, request_id, msg)
        elif cmd == "set_model":
            await self._cmd_set_model(websocket, request_id, msg)
        elif cmd == "set_audio_device":
            await self._cmd_set_audio_device(websocket, request_id, msg)
        elif cmd == "get_history":
            await self._cmd_get_history(websocket, request_id, msg)
        elif cmd == "delete_history_item":
            await self._cmd_delete_history_item(websocket, request_id, msg)
        elif cmd == "clear_history":
            await self._cmd_clear_history(websocket, request_id)
        elif cmd == "export_history":
            await self._cmd_export_history(websocket, request_id, msg)
        elif cmd == "shutdown":
            await self._cmd_shutdown(websocket, request_id)
        else:
            await self._send_error(
                websocket,
                request_id=request_id,
                code="unknown_command",
                message=f"Unknown command: {cmd}",
            )

    async def _handler(self, websocket) -> None:
        """Handle a single WebSocket connection."""
        if self._client is not None:
            await websocket.close(4000, "Only one client allowed")
            return

        self._client = websocket
        print(f"[INFO] Client connected from {websocket.remote_address}")
        self._broadcast(self._make_event("state", state="idle"))

        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send_error(
                        websocket,
                        request_id=None,
                        code="invalid_json",
                        message="Invalid JSON payload",
                    )
                    continue

                if not isinstance(msg, dict):
                    await self._send_error(
                        websocket,
                        request_id=None,
                        code="invalid_payload",
                        message="Message must be a JSON object",
                    )
                    continue

                await self._handle_command(msg, websocket)
        except Exception:
            pass  # Client disconnected.
        finally:
            self._client = None
            print("[INFO] Client disconnected")

    # --- Server lifecycle ---

    async def _start_ws(self) -> int:
        """Start WebSocket server, trying ports if busy. Returns bound port."""
        import websockets

        port = self.port
        for attempt in range(MAX_PORT_ATTEMPTS):
            try:
                self._server = await websockets.serve(self._handler, "localhost", port)
                return port
            except OSError:
                if attempt < MAX_PORT_ATTEMPTS - 1:
                    port += 1
                else:
                    raise RuntimeError(
                        f"Could not bind to any port in range "
                        f"{self.port}-{self.port + MAX_PORT_ATTEMPTS - 1}"
                    )
        return port  # Unreachable, keeps type checker happy.

    def run(self) -> None:
        """Start the server (blocking)."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        bound_port = self._loop.run_until_complete(self._start_ws())
        if bound_port != self.port:
            print(f"[WARN] Port {self.port} busy, using {bound_port}")
        self.port = bound_port
        print(f"[OK] WebSocket server listening on ws://localhost:{self.port}")

        output_config = self.config.get("output", {})

        # Create pipeline — server mode never pastes locally.
        self._pipeline = TranscriptionPipeline(
            transcriber=self._transcriber,
            dictionary=self._dictionary,
            text_inserter=self._text_inserter,
            output_fn=lambda text: None,
        )
        self._pipeline.transcription_started = self._on_transcription_started
        self._pipeline.transcription_completed = self._on_transcription_completed
        self._pipeline.error_occurred = self._on_error
        self._pipeline.start()

        # Create hotkey listener — listener-only, no transcription logic.
        self._hotkey_manager = HotkeyManager(
            hotkey_name=self.config["hotkey"]["push_to_talk"],
            recorder=self._recorder,
            pipeline=self._pipeline,
            double_tap_timeout=output_config.get("double_tap_timeout", 0.5),
        )
        self._hotkey_manager.recording_started.connect(self._on_recording_started)
        self._hotkey_manager.recording_stopped.connect(self._on_recording_stopped)

        self._hotkey_thread = threading.Thread(
            target=self._hotkey_manager.run,
            daemon=True,
        )
        self._hotkey_thread.start()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._loop.add_signal_handler(sig, self._request_shutdown)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler.
                signal.signal(sig, lambda *_: self._request_shutdown())

        try:
            self._loop.run_forever()
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Graceful shutdown of all components."""
        print("\n[INFO] Shutting down server...")

        if self._hotkey_manager:
            self._hotkey_manager.stop()
        if self._hotkey_thread and self._hotkey_thread.is_alive():
            self._hotkey_thread.join(timeout=2.0)
        if self._pipeline is not None:
            self._pipeline.stop()
        if self._server and self._loop and not self._loop.is_closed():
            self._server.close()
            self._loop.run_until_complete(self._server.wait_closed())
        if self._loop and not self._loop.is_closed():
            self._loop.close()

        print("[OK] Server stopped")
