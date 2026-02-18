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


def test_get_capabilities_response(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    monkeypatch.setattr(
        server,
        "_backend_available",
        lambda backend_id: backend_id in {"auto", "faster-whisper", "qwen-asr"},
    )
    monkeypatch.setattr(server, "_is_model_downloaded", lambda backend, name: backend != "auto")

    asyncio.run(server._handle_command({"type": "get_capabilities", "request_id": "cap-1"}, ws))

    payload = ws.sent[-1]
    _assert_ok_response(payload, "capabilities", request_id="cap-1")
    backends = payload["result"]["backends"]
    backend_ids = {entry["id"] for entry in backends}
    assert backend_ids == {"auto", "faster-whisper", "qwen-asr", "qwen-asr-vllm"}
    restart_policy = payload["result"]["restart_policy"]
    assert restart_policy["model"] is True
    assert restart_policy["dictionary"] is False
    assert len(payload["result"]["model_download_status"]) > 0
    assert payload["result"]["active_model_download"] is None
    assert "hardware" in payload["result"]
    assert "recommendation" in payload["result"]
    hw = payload["result"]["hardware"]
    assert isinstance(hw["gpu_available"], bool)
    assert hw["gpu_vendor"] in {"nvidia", "amd", "intel", "none"}
    assert isinstance(hw["gpu_name"], str)
    assert isinstance(hw["gpu_vram_gb"], (int, float))
    if payload["result"]["recommendation"] is not None:
        rec = payload["result"]["recommendation"]
        assert isinstance(rec["backend"], str)
        assert isinstance(rec["name"], str)
        assert isinstance(rec["device"], str)
        assert isinstance(rec["compute_type"], str)
        assert isinstance(rec["reason"], str)


def test_get_storage_status_uses_effective_model_cache_when_storage_root_empty(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    fake_status = {
        "storage_root": "",
        "effective_paths": {
            "model_cache_root": "D:/keyvox/models",
            "model_hub_cache": "D:/keyvox/models/hub",
            "history_db": "D:/keyvox/history/history.sqlite3",
            "exports_dir": "D:/keyvox/exports",
            "runtime_dir": "D:/keyvox/runtime",
        },
        "sizes": {
            "models_bytes": 1,
            "history_bytes": 2,
            "exports_bytes": 3,
            "runtime_bytes": 4,
            "total_bytes": 10,
        },
        "disk_free_bytes": 12345,
    }

    seen = {"target": None}

    monkeypatch.setattr(server_mod, "get_storage_status", lambda config, config_path=None: fake_status)

    def _fake_estimate(config, target_root, config_path=None):
        seen["target"] = str(target_root)
        return {"bytes_required": 10, "disk_free_bytes": 20, "breakdown": {}}

    monkeypatch.setattr(server_mod, "estimate_migration_bytes", _fake_estimate)

    asyncio.run(server._handle_command({"type": "get_storage_status", "request_id": "stor-1"}, ws))

    payload = ws.sent[-1]
    _assert_ok_response(payload, "storage_status", request_id="stor-1")
    assert seen["target"] == "D:\\keyvox\\models"


def test_list_audio_devices_success(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    fake_sounddevice = types.SimpleNamespace(
        query_devices=lambda: [
            {"name": "Output only", "max_input_channels": 0, "default_samplerate": 44100},
            {"name": "Mic A", "max_input_channels": 1, "default_samplerate": 16000},
            {"name": "Mic B", "max_input_channels": 2, "default_samplerate": 48000},
        ],
        default=types.SimpleNamespace(device=(1, 0)),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    asyncio.run(
        server._handle_command(
            {"type": "list_audio_devices", "request_id": "aud-1"},
            ws,
        )
    )

    payload = ws.sent[-1]
    _assert_ok_response(payload, "audio_devices", request_id="aud-1")
    devices = payload["result"]["devices"]
    assert len(devices) == 2
    assert devices[0]["id"] == 1
    assert devices[0]["is_default_input"] is True
    assert payload["result"]["current_input_device"] == "default"


def test_list_audio_devices_internal_error(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    fake_sounddevice = types.SimpleNamespace(
        query_devices=lambda: (_ for _ in ()).throw(RuntimeError("device backend failed")),
        default=types.SimpleNamespace(device=(0, 0)),
    )
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sounddevice)

    asyncio.run(
        server._handle_command(
            {"type": "list_audio_devices", "request_id": "aud-2"},
            ws,
        )
    )

    payload = ws.sent[-1]
    _assert_error_response(payload, "internal_error", request_id="aud-2")
    assert "enumerate audio devices" in payload["error"]["message"]


def test_validate_model_config_valid_and_invalid(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    server._hw_info["gpu_available"] = True

    asyncio.run(
        server._handle_command(
            {
                "type": "validate_model_config",
                "request_id": "val-ok",
                "backend": "faster-whisper",
                "name": " large-v3-turbo ",
                "device": "cuda",
                "compute_type": "float16",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "model_validation", request_id="val-ok")
    assert payload["result"]["valid"] is True
    assert payload["result"]["normalized"]["name"] == "large-v3-turbo"

    asyncio.run(
        server._handle_command(
            {
                "type": "validate_model_config",
                "request_id": "val-bad",
                "backend": "unknown",
                "name": "model",
                "device": "cpu",
                "compute_type": "weird",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "model_validation", request_id="val-bad")
    assert payload["result"]["valid"] is False
    assert any(item["field"] == "backend" for item in payload["result"]["errors"])
    assert any(item["field"] == "compute_type" for item in payload["result"]["errors"])


def test_validate_model_config_missing_fields_and_platform(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    monkeypatch.setattr(server_mod.platform, "system", lambda: "Windows")
    server._hw_info["gpu_available"] = False

    asyncio.run(
        server._handle_command(
            {
                "type": "validate_model_config",
                "request_id": "val-missing",
                "backend": "",
                "name": " ",
                "device": "cpu",
                "compute_type": "float16",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "model_validation", request_id="val-missing")
    assert payload["result"]["valid"] is False
    assert any(item["field"] == "backend" for item in payload["result"]["errors"])
    assert any(item["field"] == "name" for item in payload["result"]["errors"])

    asyncio.run(
        server._handle_command(
            {
                "type": "validate_model_config",
                "request_id": "val-platform",
                "backend": "qwen-asr-vllm",
                "name": "Qwen/Qwen3-ASR-1.7B",
                "device": "cuda",
                "compute_type": "bfloat16",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "model_validation", request_id="val-platform")
    assert payload["result"]["valid"] is False
    assert any(item["code"] == "unsupported_platform" for item in payload["result"]["errors"])
    assert any(item["code"] == "cuda_unavailable" for item in payload["result"]["warnings"])


def test_download_model_starts_or_returns_cached(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    calls = []

    monkeypatch.setattr(server, "_is_model_downloaded", lambda backend, name: False)

    def _fake_worker(download_id, backend, model_name):
        calls.append((download_id, backend, model_name))
        server._release_download()

    monkeypatch.setattr(server, "_run_model_download_worker", _fake_worker)

    class _InlineThread:
        def __init__(self, target, args, daemon):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    monkeypatch.setattr(server_mod.threading, "Thread", _InlineThread)

    asyncio.run(
        server._handle_command(
            {
                "type": "download_model",
                "request_id": "dl-1",
                "backend": "qwen-asr",
                "name": "Qwen/Qwen3-ASR-1.7B",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "model_download_started", request_id="dl-1")
    assert payload["result"]["started"] is True
    assert len(calls) == 1
    assert calls[0][1:] == ("qwen-asr", "Qwen/Qwen3-ASR-1.7B")

    monkeypatch.setattr(server, "_is_model_downloaded", lambda backend, name: True)
    asyncio.run(
        server._handle_command(
            {
                "type": "download_model",
                "request_id": "dl-2",
                "backend": "qwen-asr",
                "name": "Qwen/Qwen3-ASR-1.7B",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_ok_response(payload, "model_download_started", request_id="dl-2")
    assert payload["result"]["started"] is False
    assert payload["result"]["already_downloaded"] is True


def test_download_model_in_progress_and_validation(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    monkeypatch.setattr(server, "_is_model_downloaded", lambda backend, name: False)

    assert server._reserve_download("faster-whisper", "large-v3-turbo") is True
    asyncio.run(
        server._handle_command(
            {
                "type": "download_model",
                "request_id": "dl-busy",
                "backend": "qwen-asr",
                "name": "Qwen/Qwen3-ASR-1.7B",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_error_response(payload, "download_in_progress", request_id="dl-busy")
    server._release_download()

    asyncio.run(
        server._handle_command(
            {
                "type": "download_model",
                "request_id": "dl-invalid",
                "backend": "auto",
                "name": "large-v3-turbo",
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    _assert_error_response(payload, "invalid_payload", request_id="dl-invalid")


def test_run_model_download_worker_emits_events(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    events = []
    monkeypatch.setattr(server, "_broadcast", lambda payload: events.append(payload))

    def _fake_snapshot(*, download_id, backend, model_name):
        server._broadcast_model_download(
            download_id=download_id,
            status="completed",
            backend=backend,
            name=model_name,
            message="Model downloaded.",
            progress_pct=100,
        )
        return "Qwen/Qwen3-ASR-1.7B", 0, 0

    monkeypatch.setattr(server, "_download_model_snapshot", _fake_snapshot)
    assert server._reserve_download("qwen-asr", "Qwen/Qwen3-ASR-1.7B") is True

    server._run_model_download_worker("dl-1", "qwen-asr", "Qwen/Qwen3-ASR-1.7B")

    statuses = [event["status"] for event in events if event["type"] == "model_download"]
    assert statuses == ["starting", "completed"]


def test_set_storage_root_rejects_when_destination_space_insufficient(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()

    monkeypatch.setattr(
        server_mod,
        "estimate_migration_bytes",
        lambda config, target_root, config_path=None: {
            "bytes_required": 10_000,
            "disk_free_bytes": 512,
            "breakdown": {"model_cache_root": 10_000},
        },
    )

    thread_created = {"value": False}

    class _ThreadGuard:
        def __init__(self, *args, **kwargs):
            thread_created["value"] = True

        def start(self):
            raise AssertionError("Storage migration worker should not start")

    monkeypatch.setattr(server_mod.threading, "Thread", _ThreadGuard)

    asyncio.run(
        server._handle_command(
            {
                "type": "set_storage_root",
                "request_id": "storage-1",
                "storage_root": "D:/tmp/keyvox-storage",
            },
            ws,
        )
    )

    payload = ws.sent[-1]
    _assert_error_response(payload, "insufficient_space", request_id="storage-1")
    assert thread_created["value"] is False
    assert server._get_active_storage_target() is None


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


# ---------------------------------------------------------------------------
# Input validation error paths
# ---------------------------------------------------------------------------

def test_get_history_rejects_negative_limit(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "get_history", "request_id": "h-lim", "limit": -1, "offset": 0},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="h-lim")


def test_get_history_rejects_negative_offset(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "get_history", "request_id": "h-off", "limit": 10, "offset": -1},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="h-off")


def test_get_history_rejects_non_string_search(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "get_history", "request_id": "h-srch", "limit": 10, "offset": 0, "search": 42},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="h-srch")


def test_delete_history_item_rejects_zero_id(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "delete_history_item", "request_id": "d-zero", "id": 0},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="d-zero")


def test_delete_history_item_returns_not_found(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "delete_history_item", "request_id": "d-nf", "id": 9999},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "not_found", request_id="d-nf")


def test_export_history_rejects_invalid_format(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    monkeypatch.setattr(server_mod, "get_config_path", lambda: None)
    asyncio.run(
        server._handle_command(
            {"type": "export_history", "request_id": "exp-fmt", "format": "xml"},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="exp-fmt")


def test_set_dictionary_rejects_empty_value(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "set_dictionary", "request_id": "dict-empty", "key": "foo", "value": ""},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="dict-empty")


def test_delete_dictionary_returns_not_found_for_missing_key(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "delete_dictionary", "request_id": "dict-nf", "key": "doesnotexist"},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "not_found", request_id="dict-nf")


def test_set_config_section_rejects_unknown_section(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {
                "type": "set_config_section",
                "request_id": "sec-bad",
                "section": "nonexistent_section",
                "values": {"foo": "bar"},
            },
            ws,
        )
    )
    payload = ws.sent[-1]
    assert payload["ok"] is False
    assert payload["error"]["code"] in {"invalid_section", "invalid_payload"}


def test_set_model_rejects_when_no_fields_provided(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "set_model", "request_id": "mod-empty"},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="mod-empty")


def test_set_audio_device_rejects_non_positive_sample_rate(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "set_audio_device", "request_id": "aud-rate", "sample_rate": -1},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="aud-rate")


def test_set_audio_device_rejects_no_fields(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "set_audio_device", "request_id": "aud-none"},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="aud-none")


def test_set_storage_root_rejects_empty_string(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    asyncio.run(
        server._handle_command(
            {"type": "set_storage_root", "request_id": "stor-empty", "storage_root": "   "},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id="stor-empty")


def test_coerce_request_id_rejects_list(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    ws = _FakeWebSocket()
    # A list request_id raises ValueError in _coerce_request_id → invalid_payload
    asyncio.run(
        server._handle_command(
            {"type": "ping", "request_id": [1, 2]},
            ws,
        )
    )
    _assert_error_response(ws.sent[-1], "invalid_payload", request_id=None)


# ---------------------------------------------------------------------------
# Migration worker
# ---------------------------------------------------------------------------

def test_run_storage_migration_worker_success_emits_events(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    events = []
    monkeypatch.setattr(server, "_broadcast", lambda payload: events.append(payload))

    def fake_migrate(config, root, config_path=None, progress_cb=None):
        if progress_cb:
            progress_cb(
                {
                    "status": "copying",
                    "message": "Copying files",
                    "progress_pct": 50,
                    "total_bytes": 100,
                    "copied_bytes": 50,
                }
            )
        return {
            "bytes_required": 100,
            "disk_free_bytes": 10_000,
            "moved": {},
            "completed_at": 0,
            "storage_root": str(root),
        }

    monkeypatch.setattr(server_mod, "migrate_storage_root", fake_migrate)

    class _HistoryFactory:
        @staticmethod
        def from_config(_):
            return _FakeHistoryStore()

    monkeypatch.setattr(server_mod, "HistoryStore", _HistoryFactory)
    monkeypatch.setattr(server_mod, "get_config_path", lambda: None)

    server._run_storage_migration_worker("D:/target")

    statuses = [e.get("status") for e in events if e.get("type") == "storage_migration"]
    assert "starting" in statuses
    assert "completed" in statuses
    assert server._get_active_storage_target() is None


def test_run_storage_migration_worker_failure_emits_failed_event(monkeypatch):
    server, _, _ = _make_server(monkeypatch)
    events = []
    monkeypatch.setattr(server, "_broadcast", lambda payload: events.append(payload))

    monkeypatch.setattr(
        server_mod,
        "migrate_storage_root",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk exploded")),
    )
    monkeypatch.setattr(server_mod, "get_config_path", lambda: None)

    server._run_storage_migration_worker("D:/target")

    failed_events = [e for e in events if e.get("type") == "storage_migration" and e.get("status") == "failed"]
    assert len(failed_events) == 1
    assert "disk exploded" in failed_events[0]["message"]
    assert server._get_active_storage_target() is None
