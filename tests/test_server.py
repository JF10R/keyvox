"""Tests for WebSocket server mode."""
import asyncio
import json
import sys
import types
from pathlib import Path

import keyvox.server as server_mod
from keyvox.server import KeyvoxServer, PROTOCOL_VERSION


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
        "paths": {},
        "text_insertion": {"enabled": True},
        "dictionary": {"github": "GitHub"},
    }


class _FakeDictionary:
    def __init__(self, corrections):
        self.corrections = dict(corrections)


class _FakeTextInserter:
    def __init__(self, config, dictionary_corrections):
        self.config = config
        self.dictionary_corrections = dict(dictionary_corrections)


class _FakeHistoryStore:
    def __init__(self):
        self.db_path = Path("D:/tmp/history.sqlite3")
        self.entries = []
        self._next_id = 1

    def add_entry(self, *, text, duration_ms, backend, model, status="ok"):
        entry = {
            "id": self._next_id,
            "created_at": "2026-02-17 00:00:00",
            "text": text,
            "duration_ms": duration_ms,
            "backend": backend,
            "model": model,
            "status": status,
        }
        self._next_id += 1
        self.entries.append(entry)
        return dict(entry)

    def list_entries(self, *, limit=100, offset=0, search=""):
        items = [entry for entry in self.entries if search.lower() in entry["text"].lower()]
        return [dict(entry) for entry in list(reversed(items))[offset: offset + limit]]

    def count_entries(self, *, search=""):
        return len([entry for entry in self.entries if search.lower() in entry["text"].lower()])

    def delete_entry(self, entry_id):
        before = len(self.entries)
        self.entries = [entry for entry in self.entries if entry["id"] != entry_id]
        return len(self.entries) != before

    def clear(self):
        count = len(self.entries)
        self.entries = []
        return count

    def export_txt(self, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("txt-export", encoding="utf-8")
        return output_path

    def export_csv(self, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("csv-export", encoding="utf-8")
        return output_path


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


def _assert_ok_response(payload, response_type, request_id=None):
    assert payload["type"] == "response"
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["ok"] is True
    assert payload["response_type"] == response_type
    assert payload["request_id"] == request_id
    assert isinstance(payload["result"], dict)


def _assert_error_response(payload, code, request_id=None):
    assert payload["type"] == "response"
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["ok"] is False
    assert payload["response_type"] == "error"
    assert payload["request_id"] == request_id
    assert payload["error"]["code"] == code


def _make_server(monkeypatch, config=None):
    cfg = config or _base_config()
    fake_dictionary = _FakeDictionary(cfg.get("dictionary", {}))
    fake_history = _FakeHistoryStore()

    class _DictManager:
        @staticmethod
        def load_from_config(config_dict):
            return _FakeDictionary(config_dict.get("dictionary", {}))

    class _HistoryFactory:
        @staticmethod
        def from_config(_):
            return fake_history

    monkeypatch.setattr(server_mod, "create_transcriber", lambda _: "TRANSCRIBER")
    monkeypatch.setattr(
        server_mod,
        "AudioRecorder",
        lambda sample_rate, input_device: ("REC", sample_rate, input_device),
    )
    monkeypatch.setattr(server_mod, "DictionaryManager", _DictManager)
    monkeypatch.setattr(server_mod, "TextInserter", _FakeTextInserter)
    monkeypatch.setattr(server_mod, "HistoryStore", _HistoryFactory)

    server = KeyvoxServer(config=cfg, port=9876)
    return server, fake_dictionary, fake_history


def test_get_config_response_envelope(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    asyncio.run(server._handle_command({"type": "get_config", "request_id": "cfg-1"}, ws))

    payload = ws.sent[-1]
    _assert_ok_response(payload, "config", request_id="cfg-1")
    assert payload["result"]["hotkey"] == "ctrl_r"
    assert payload["result"]["backend"] == "faster-whisper"


def test_handler_rejects_second_client(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    server._client = object()
    ws = _FakeWebSocket()

    asyncio.run(server._handler(ws))

    assert ws.closed == (4000, "Only one client allowed")


def test_handler_returns_protocol_errors_for_bad_payloads(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket(
        incoming=[
            "not-json",
            json.dumps(["not", "an", "object"]),
            json.dumps({"type": 1}),
        ]
    )

    asyncio.run(server._handler(ws))

    _assert_error_response(ws.sent[0], "invalid_json")
    _assert_error_response(ws.sent[1], "invalid_payload")
    _assert_error_response(ws.sent[2], "invalid_payload")


def test_unknown_command_returns_unknown_command_code(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    asyncio.run(server._handle_command({"type": "does_not_exist", "request_id": 9}, ws))

    payload = ws.sent[-1]
    _assert_error_response(payload, "unknown_command", request_id=9)
    assert payload["error"]["message"] == "Unknown command: does_not_exist"


def test_set_and_delete_dictionary(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    saved = []

    monkeypatch.setattr(server_mod, "get_config_path", lambda: Path("D:/tmp/config.toml"))
    monkeypatch.setattr(
        server_mod,
        "save_config",
        lambda path, cfg: saved.append((path, dict(cfg["dictionary"]))),
    )

    asyncio.run(
        server._handle_command(
            {
                "type": "set_dictionary",
                "request_id": "dict1",
                "key": " OpenAI ",
                "value": "OpenAI",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "dictionary_updated", request_id="dict1")
    assert server.config["dictionary"]["openai"] == "OpenAI"
    assert saved[-1][1]["openai"] == "OpenAI"

    asyncio.run(
        server._handle_command(
            {
                "type": "delete_dictionary",
                "request_id": "dict2",
                "key": "openai",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "dictionary_deleted", request_id="dict2")
    assert "openai" not in server.config["dictionary"]


def test_get_history_and_delete_item(monkeypatch):
    server, _, history = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    history.add_entry(
        text="first",
        duration_ms=101,
        backend="faster-whisper",
        model="small",
    )
    entry2 = history.add_entry(
        text="second",
        duration_ms=202,
        backend="faster-whisper",
        model="small",
    )

    asyncio.run(
        server._handle_command(
            {
                "type": "get_history",
                "request_id": "h1",
                "limit": 10,
                "offset": 0,
                "search": "sec",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "history", request_id="h1")
    assert payload["result"]["total"] == 1
    assert payload["result"]["entries"][0]["id"] == entry2["id"]

    asyncio.run(
        server._handle_command(
            {"type": "delete_history_item", "request_id": "h2", "id": entry2["id"]},
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "history_item_deleted", request_id="h2")
    assert all(item["id"] != entry2["id"] for item in history.entries)


def test_clear_history_and_export(monkeypatch, tmp_path):
    server, _, history = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    history.add_entry(
        text="one",
        duration_ms=1,
        backend="faster-whisper",
        model="small",
    )

    asyncio.run(server._handle_command({"type": "clear_history", "request_id": "c1"}, ws))
    payload = ws.sent[-1]
    _assert_ok_response(payload, "history_cleared", request_id="c1")
    assert payload["result"]["removed"] == 1
    assert history.entries == []

    asyncio.run(
        server._handle_command(
            {
                "type": "export_history",
                "request_id": "c2",
                "format": "csv",
                "path": str(tmp_path / "export.csv"),
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "history_exported", request_id="c2")
    assert payload["result"]["format"] == "csv"
    assert Path(payload["result"]["path"]).exists()


def test_config_update_commands(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    monkeypatch.setattr(server_mod, "get_config_path", lambda: Path("D:/tmp/config.toml"))
    monkeypatch.setattr(server_mod, "save_config", lambda path, cfg: None)

    asyncio.run(
        server._handle_command(
            {
                "type": "set_config_section",
                "request_id": "s1",
                "section": "text_insertion",
                "values": {"enabled": False},
            },
            ws,
        )
    )
    _assert_ok_response(ws.sent[-1], "config_section_updated", request_id="s1")
    assert server.config["text_insertion"]["enabled"] is False

    asyncio.run(
        server._handle_command(
            {"type": "set_hotkey", "request_id": "s2", "hotkey": "alt_l"},
            ws,
        )
    )
    _assert_ok_response(ws.sent[-1], "hotkey_updated", request_id="s2")
    assert server.config["hotkey"]["push_to_talk"] == "alt_l"

    asyncio.run(
        server._handle_command(
            {
                "type": "set_model",
                "request_id": "s3",
                "backend": "qwen-asr",
                "name": "Qwen/Qwen3-ASR-1.7B",
            },
            ws,
        )
    )
    _assert_ok_response(ws.sent[-1], "model_updated", request_id="s3")
    assert server.config["model"]["backend"] == "qwen-asr"

    asyncio.run(
        server._handle_command(
            {
                "type": "set_audio_device",
                "request_id": "s4",
                "input_device": 2,
                "sample_rate": 22050,
            },
            ws,
        )
    )
    _assert_ok_response(ws.sent[-1], "audio_updated", request_id="s4")
    assert server.config["audio"]["input_device"] == 2
    assert server.config["audio"]["sample_rate"] == 22050


def test_ping_and_server_info(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    asyncio.run(server._handle_command({"type": "ping", "request_id": "p1"}, ws))
    _assert_ok_response(ws.sent[-1], "pong", request_id="p1")
    assert ws.sent[-1]["result"]["pong"] is True

    asyncio.run(server._handle_command({"type": "server_info", "request_id": "p2"}, ws))
    _assert_ok_response(ws.sent[-1], "server_info", request_id="p2")
    assert ws.sent[-1]["result"]["protocol_version"] == PROTOCOL_VERSION


def test_shutdown_command_requests_server_stop(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    called = {"shutdown": False}

    monkeypatch.setattr(server, "_request_shutdown", lambda: called.__setitem__("shutdown", True))

    asyncio.run(server._handle_command({"type": "shutdown", "request_id": "bye"}, ws))

    payload = ws.sent[-1]
    _assert_ok_response(payload, "shutting_down", request_id="bye")
    assert called["shutdown"] is True


def test_transcription_callback_adds_history_and_emits_events(monkeypatch):
    server, _, history = _make_server(monkeypatch)
    events = []
    monkeypatch.setattr(server, "_broadcast", lambda payload: events.append(payload))
    server._recording_started_at = 1.0
    monkeypatch.setattr(server_mod.time, "monotonic", lambda: 1.2)

    server._on_transcription_completed("hello")

    assert history.entries[-1]["text"] == "hello"
    assert events[0]["type"] == "transcription"
    assert events[0]["entry"]["text"] == "hello"
    assert events[1]["type"] == "history_appended"
    assert events[2]["type"] == "state"
    assert events[2]["state"] == "idle"
    assert events[2]["protocol_version"] == PROTOCOL_VERSION


def test_create_hotkey_manager_disables_local_output(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    captured = {}

    class _FakeHotkeyManager:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server_mod, "HotkeyManager", _FakeHotkeyManager)

    server._create_hotkey_manager()

    assert captured["auto_paste"] is False
    assert captured["double_tap_to_clipboard"] is False


def test_start_ws_falls_back_to_next_port(monkeypatch):
    server, _, _ = _make_server(monkeypatch, config=_base_config())
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
