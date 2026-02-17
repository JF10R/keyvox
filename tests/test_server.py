"""Tests for WebSocket server mode."""
import asyncio
import json
import sys
import types
from pathlib import Path

import keyvox.server as server_mod
from keyvox.server import KeyvoxServer


def _base_config():
    return {
        "model": {"backend": "faster-whisper", "name": "large-v3-turbo"},
        "audio": {"sample_rate": 16000, "input_device": "default"},
        "hotkey": {"push_to_talk": "ctrl_r"},
        "output": {
            "auto_paste": True,
            "paste_method": "clipboard",
            "double_tap_to_clipboard": True,
            "double_tap_timeout": 0.5,
        },
        "text_insertion": {"enabled": True},
        "dictionary": {"github": "GitHub"},
    }


class _FakeDictionary:
    def __init__(self, corrections):
        self.corrections = dict(corrections)
        self.compile_calls = 0
        self._pattern = None

    def _compile_pattern(self):
        self.compile_calls += 1
        return f"compiled-{self.compile_calls}"


class _FakeTextInserter:
    def __init__(self, config, dictionary_corrections):
        self.config = config
        self.dictionary_corrections = dict(dictionary_corrections)


class _FakeWebSocket:
    def __init__(self, incoming=None):
        self._incoming = list(incoming or [])
        self.sent = []
        self.closed = None
        self.remote_address = ("127.0.0.1", 12345)

    async def send(self, data):
        self.sent.append(json.loads(data))

    async def close(self, code, reason):
        self.closed = (code, reason)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)


def _make_server(monkeypatch, config=None):
    cfg = config or _base_config()
    fake_dictionary = _FakeDictionary(cfg.get("dictionary", {}))

    class _DictManager:
        @staticmethod
        def load_from_config(_):
            return fake_dictionary

    monkeypatch.setattr(server_mod, "create_transcriber", lambda _: "TRANSCRIBER")
    monkeypatch.setattr(server_mod, "AudioRecorder", lambda sample_rate, input_device: ("REC", sample_rate, input_device))
    monkeypatch.setattr(server_mod, "DictionaryManager", _DictManager)
    monkeypatch.setattr(server_mod, "TextInserter", _FakeTextInserter)

    server = KeyvoxServer(config=cfg, port=9876)
    return server, fake_dictionary


def test_handle_command_get_config(monkeypatch):
    server, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    asyncio.run(server._handle_command({"type": "get_config"}, ws))

    assert ws.sent == [{
        "type": "config",
        "hotkey": "ctrl_r",
        "backend": "faster-whisper",
        "model": "large-v3-turbo",
    }]


def test_handle_command_invalid_and_unknown(monkeypatch):
    server, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    asyncio.run(server._handle_command({"type": 123}, ws))
    asyncio.run(server._handle_command({"type": "nope"}, ws))

    assert ws.sent[0] == {
        "type": "error",
        "message": "Command 'type' must be a non-empty string",
    }
    assert ws.sent[1] == {
        "type": "error",
        "message": "Unknown command: nope",
    }


def test_handler_rejects_second_client(monkeypatch):
    server, _ = _make_server(monkeypatch)
    server._client = object()
    ws = _FakeWebSocket()

    asyncio.run(server._handler(ws))

    assert ws.closed == (4000, "Only one client allowed")


def test_handler_returns_error_for_bad_payload_shapes(monkeypatch):
    server, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket(
        incoming=[
            "not-json",
            json.dumps(["not", "an", "object"]),
            json.dumps({"type": "get_dictionary"}),
        ]
    )

    asyncio.run(server._handler(ws))

    assert ws.sent[0] == {"type": "error", "message": "Invalid JSON payload"}
    assert ws.sent[1] == {"type": "error", "message": "Message must be a JSON object"}
    assert ws.sent[2]["type"] == "dictionary"


def test_set_dictionary_updates_runtime_and_persists(monkeypatch):
    server, fake_dictionary = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    saved = []

    monkeypatch.setattr(server_mod, "get_config_path", lambda: Path("D:/tmp/config.toml"))
    monkeypatch.setattr(server_mod, "save_config", lambda path, cfg: saved.append((path, dict(cfg["dictionary"]))))

    asyncio.run(server._handle_command({"type": "set_dictionary", "key": "  openai ", "value": " OpenAI "}, ws))

    assert fake_dictionary.corrections["openai"] == "OpenAI"
    assert fake_dictionary.compile_calls == 1
    assert saved == [(Path("D:/tmp/config.toml"), {"github": "GitHub", "openai": "OpenAI"})]
    assert server._text_inserter.dictionary_corrections["openai"] == "OpenAI"
    assert ws.sent[-1] == {"type": "dictionary_updated", "key": "openai", "value": "OpenAI"}


def test_delete_dictionary_validates_key_and_persists(monkeypatch):
    server, fake_dictionary = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    saved = []

    monkeypatch.setattr(server_mod, "get_config_path", lambda: Path("D:/tmp/config.toml"))
    monkeypatch.setattr(server_mod, "save_config", lambda path, cfg: saved.append((path, dict(cfg["dictionary"]))))

    asyncio.run(server._handle_command({"type": "delete_dictionary", "key": "missing"}, ws))
    assert ws.sent[-1] == {"type": "error", "message": "Key 'missing' not found in dictionary"}

    asyncio.run(server._handle_command({"type": "delete_dictionary", "key": "github"}, ws))
    assert "github" not in fake_dictionary.corrections
    assert fake_dictionary.compile_calls == 1
    assert saved[-1] == (Path("D:/tmp/config.toml"), {})
    assert ws.sent[-1] == {"type": "dictionary_deleted", "key": "github"}


def test_shutdown_command_requests_server_stop(monkeypatch):
    server, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    called = {"shutdown": False}

    monkeypatch.setattr(server, "_request_shutdown", lambda: called.__setitem__("shutdown", True))

    asyncio.run(server._handle_command({"type": "shutdown"}, ws))

    assert ws.sent[-1] == {"type": "shutting_down"}
    assert called["shutdown"] is True


def test_state_callbacks_emit_expected_events(monkeypatch):
    server, _ = _make_server(monkeypatch)
    events = []
    monkeypatch.setattr(server, "_broadcast", lambda payload: events.append(payload))

    server._on_recording_started()
    server._on_transcription_started()
    server._on_transcription_completed("hello")
    server._on_error("boom")

    assert events == [
        {"type": "state", "state": "recording"},
        {"type": "state", "state": "processing"},
        {"type": "transcription", "text": "hello"},
        {"type": "state", "state": "idle"},
        {"type": "error", "message": "boom"},
        {"type": "state", "state": "idle"},
    ]


def test_create_hotkey_manager_disables_local_output(monkeypatch):
    server, _ = _make_server(monkeypatch)
    captured = {}

    class _FakeHotkeyManager:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server_mod, "HotkeyManager", _FakeHotkeyManager)

    server._create_hotkey_manager()

    assert captured["auto_paste"] is False
    assert captured["double_tap_to_clipboard"] is False


def test_start_ws_falls_back_to_next_port(monkeypatch):
    server, _ = _make_server(monkeypatch, config=_base_config())
    server.port = 7000
    calls = []

    class _FakeWsServer:
        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def _serve(handler, host, port):
        calls.append((host, port))
        if port == 7000:
            raise OSError("busy")
        return _FakeWsServer()

    monkeypatch.setitem(sys.modules, "websockets", types.SimpleNamespace(serve=_serve))

    bound_port = asyncio.run(server._start_ws())

    assert bound_port == 7001
    assert calls == [("localhost", 7000), ("localhost", 7001)]
    assert server._server is not None
