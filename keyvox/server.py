"""WebSocket server exposing the Keyvox engine over ws://localhost:<port>.

Broadcasts state transitions and transcription results to a single client.
Accepts commands: get_config, get_dictionary, set_dictionary, delete_dictionary, shutdown.
"""
import asyncio
import json
import signal
import threading
from typing import Any, Dict, Optional

from .config import save_config, get_config_path
from .recorder import AudioRecorder
from .backends import create_transcriber
from .hotkey import HotkeyManager
from .dictionary import DictionaryManager
from .text_insertion import TextInserter

DEFAULT_PORT = 9876
MAX_PORT_ATTEMPTS = 10


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

        # Initialize engine components
        self._transcriber = create_transcriber(config)
        self._recorder = AudioRecorder(
            sample_rate=config["audio"]["sample_rate"],
            input_device=config["audio"]["input_device"],
        )
        self._dictionary = DictionaryManager.load_from_config(config)
        ti_config = config.get("text_insertion", {})
        self._text_inserter = TextInserter(
            config=ti_config,
            dictionary_corrections=self._dictionary.corrections,
        )

    # --- Engine event handlers → WebSocket broadcast ---

    def _on_recording_started(self) -> None:
        self._broadcast({"type": "state", "state": "recording"})

    def _on_recording_stopped(self) -> None:
        pass  # Processing state is emitted by transcription_started

    def _on_transcription_started(self) -> None:
        self._broadcast({"type": "state", "state": "processing"})

    def _on_transcription_completed(self, text: str) -> None:
        self._broadcast({"type": "transcription", "text": text})
        self._broadcast({"type": "state", "state": "idle"})

    def _on_error(self, error_msg: str) -> None:
        self._broadcast({"type": "error", "message": error_msg})
        self._broadcast({"type": "state", "state": "idle"})

    def _broadcast(self, message: Dict[str, Any]) -> None:
        """Send JSON message to connected client (thread-safe)."""
        if self._client is None or self._loop is None or self._loop.is_closed():
            return
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

    # --- WebSocket handler ---

    async def _handler(self, websocket) -> None:
        """Handle a single WebSocket connection."""
        if self._client is not None:
            await websocket.close(4000, "Only one client allowed")
            return

        self._client = websocket
        print(f"[INFO] Client connected from {websocket.remote_address}")
        self._broadcast({"type": "state", "state": "idle"})

        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await self._send_error(websocket, "Invalid JSON payload")
                    continue

                if not isinstance(msg, dict):
                    await self._send_error(websocket, "Message must be a JSON object")
                    continue

                await self._handle_command(msg, websocket)
        except Exception:
            pass  # Client disconnected
        finally:
            self._client = None
            print("[INFO] Client disconnected")

    async def _send_error(self, websocket, message: str) -> None:
        await websocket.send(json.dumps({"type": "error", "message": message}))

    def _sync_dictionary_runtime(self) -> None:
        self._dictionary._pattern = self._dictionary._compile_pattern()
        self._persist_dictionary()
        self._text_inserter = TextInserter(
            config=self.config.get("text_insertion", {}),
            dictionary_corrections=self._dictionary.corrections,
        )
        if self._hotkey_manager:
            self._hotkey_manager.dictionary = self._dictionary
            self._hotkey_manager.text_inserter = self._text_inserter

    async def _handle_command(self, msg: Dict[str, Any], websocket) -> None:
        """Route incoming command to handler."""
        cmd = msg.get("type")
        if not isinstance(cmd, str) or not cmd:
            await self._send_error(websocket, "Command 'type' must be a non-empty string")
            return

        if cmd == "get_config":
            await websocket.send(json.dumps({
                "type": "config",
                "hotkey": self.config["hotkey"]["push_to_talk"],
                "backend": self.config["model"]["backend"],
                "model": self.config["model"]["name"],
            }))

        elif cmd == "get_dictionary":
            await websocket.send(json.dumps({
                "type": "dictionary",
                "entries": self._dictionary.corrections,
            }))

        elif cmd == "set_dictionary":
            key_raw = msg.get("key")
            value_raw = msg.get("value")
            key = key_raw.strip().lower() if isinstance(key_raw, str) else ""
            value = value_raw.strip() if isinstance(value_raw, str) else ""
            if not key or not value:
                await self._send_error(
                    websocket,
                    "set_dictionary requires non-empty string 'key' and 'value'",
                )
                return
            self._dictionary.corrections[key] = value
            self._sync_dictionary_runtime()
            await websocket.send(json.dumps({
                "type": "dictionary_updated",
                "key": key, "value": value,
            }))

        elif cmd == "delete_dictionary":
            key_raw = msg.get("key")
            key = key_raw.strip().lower() if isinstance(key_raw, str) else ""
            if not key or key not in self._dictionary.corrections:
                await self._send_error(websocket, f"Key '{key}' not found in dictionary")
                return
            del self._dictionary.corrections[key]
            self._sync_dictionary_runtime()
            await websocket.send(json.dumps({
                "type": "dictionary_deleted", "key": key,
            }))

        elif cmd == "shutdown":
            await websocket.send(json.dumps({"type": "shutting_down"}))
            print("[INFO] Shutdown requested by client")
            self._request_shutdown()

        else:
            await self._send_error(websocket, f"Unknown command: {cmd}")

    def _persist_dictionary(self) -> None:
        """Save current dictionary corrections to config.toml."""
        config_path = get_config_path()
        if config_path is None:
            print("[WARN] No config file found, dictionary changes are in-memory only")
            return
        self.config["dictionary"] = self._dictionary.corrections
        try:
            save_config(config_path, self.config)
        except Exception as e:
            print(f"[WARN] Failed to save dictionary to config: {e}")

    # --- Server lifecycle ---

    def _request_shutdown(self) -> None:
        """Schedule graceful shutdown."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

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
                self._server = await websockets.serve(
                    self._handler, "localhost", port
                )
                return port
            except OSError:
                if attempt < MAX_PORT_ATTEMPTS - 1:
                    port += 1
                else:
                    raise RuntimeError(
                        f"Could not bind to any port in range "
                        f"{self.port}-{self.port + MAX_PORT_ATTEMPTS - 1}"
                    )
        return port  # unreachable, but satisfies type checker

    def run(self) -> None:
        """Start the server (blocking)."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Start WebSocket server
        bound_port = self._loop.run_until_complete(self._start_ws())
        if bound_port != self.port:
            print(f"[WARN] Port {self.port} busy, using {bound_port}")
        self.port = bound_port

        print(f"[OK] WebSocket server listening on ws://localhost:{self.port}")

        # Wire up hotkey events
        self._hotkey_manager = self._create_hotkey_manager()
        self._hotkey_manager.recording_started.connect(self._on_recording_started)
        self._hotkey_manager.recording_stopped.connect(self._on_recording_stopped)
        self._hotkey_manager.transcription_started.connect(self._on_transcription_started)
        self._hotkey_manager.transcription_completed.connect(self._on_transcription_completed)
        self._hotkey_manager.error_occurred.connect(self._on_error)

        # Run hotkey listener in background thread
        self._hotkey_thread = threading.Thread(
            target=self._hotkey_manager.run, daemon=True
        )
        self._hotkey_thread.start()

        # Handle Ctrl+C
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._loop.add_signal_handler(sig, self._request_shutdown)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig, lambda *_: self._request_shutdown())

        # Run event loop until shutdown
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
