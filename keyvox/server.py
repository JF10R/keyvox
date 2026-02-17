"""WebSocket server exposing the Keyvox engine over ws://localhost:<port>."""
from __future__ import annotations

import asyncio
import json
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
from .recorder import AudioRecorder
from .text_insertion import TextInserter

DEFAULT_PORT = 9876
MAX_PORT_ATTEMPTS = 10
PROTOCOL_VERSION = "1.0.0"
DEFAULT_HISTORY_LIMIT = 100


class KeyvoxServer:
    """WebSocket server wrapping the Keyvox engine pipeline."""

    def __init__(self, config: Dict[str, Any], port: int = DEFAULT_PORT):
        self.config = config
        self.port = port
        self._client = None  # Single connected client
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._hotkey_manager: Optional[HotkeyManager] = None
        self._hotkey_thread: Optional[threading.Thread] = None
        self._server = None
        self._recording_started_at: Optional[float] = None

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
        self._dictionary = DictionaryManager.load_from_config(self.config)
        self._text_inserter = TextInserter(
            config=self.config.get("text_insertion", {}),
            dictionary_corrections=self._dictionary.corrections,
        )
        if self._hotkey_manager:
            self._hotkey_manager.dictionary = self._dictionary
            self._hotkey_manager.text_inserter = self._text_inserter

    def _default_export_path(self, export_format: str) -> Path:
        base_dir = Path.cwd()
        config_path = get_config_path()
        if config_path is not None:
            base_dir = config_path.parent
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return base_dir / f"keyvox-history-{timestamp}.{export_format}"

    def _request_shutdown(self) -> None:
        """Schedule graceful shutdown."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

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

    def _create_hotkey_manager(self) -> HotkeyManager:
        output_config = self.config.get("output", {})
        # Server mode is engine-only: never type/paste into local active window.
        return HotkeyManager(
            hotkey_name=self.config["hotkey"]["push_to_talk"],
            recorder=self._recorder,
            transcriber=self._transcriber,
            dictionary=self._dictionary,
            auto_paste=False,
            paste_method=output_config.get("paste_method", "type"),
            double_tap_to_clipboard=False,
            double_tap_timeout=output_config.get("double_tap_timeout", 0.5),
            text_inserter=self._text_inserter,
        )

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

        self._hotkey_manager = self._create_hotkey_manager()
        self._hotkey_manager.recording_started.connect(self._on_recording_started)
        self._hotkey_manager.recording_stopped.connect(self._on_recording_stopped)
        self._hotkey_manager.transcription_started.connect(self._on_transcription_started)
        self._hotkey_manager.transcription_completed.connect(self._on_transcription_completed)
        self._hotkey_manager.error_occurred.connect(self._on_error)

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
        if self._server and self._loop and not self._loop.is_closed():
            self._server.close()
            self._loop.run_until_complete(self._server.wait_closed())
        if self._loop and not self._loop.is_closed():
            self._loop.close()

        print("[OK] Server stopped")
