"""Tests for SQLite transcription history storage."""
from pathlib import Path

from keyvox.history import HistoryStore, MAX_HISTORY_LIMIT


def test_add_list_and_count_entries(tmp_path):
    store = HistoryStore(tmp_path / "history.sqlite3")
    store.add_entry(
        text="first item",
        duration_ms=900,
        backend="faster-whisper",
        model="large-v3-turbo",
    )
    store.add_entry(
        text="second item",
        duration_ms=None,
        backend="qwen-asr",
        model="Qwen/Qwen3-ASR-1.7B",
    )

    entries = store.list_entries(limit=10)
    assert len(entries) == 2
    assert entries[0]["text"] == "second item"
    assert entries[1]["text"] == "first item"
    assert store.count_entries() == 2


def test_search_limit_and_offset(tmp_path):
    store = HistoryStore(tmp_path / "history.sqlite3")
    for idx in range(5):
        store.add_entry(
            text=f"keyword #{idx}",
            duration_ms=idx * 10,
            backend="faster-whisper",
            model="base",
        )
    store.add_entry(
        text="something else",
        duration_ms=1,
        backend="faster-whisper",
        model="base",
    )

    filtered = store.list_entries(search="keyword", limit=2, offset=1)
    assert len(filtered) == 2
    assert all("keyword" in item["text"] for item in filtered)
    assert store.count_entries(search="keyword") == 5


def test_limit_is_bounded(tmp_path):
    store = HistoryStore(tmp_path / "history.sqlite3")
    for idx in range(MAX_HISTORY_LIMIT + 20):
        store.add_entry(
            text=f"line {idx}",
            duration_ms=None,
            backend="faster-whisper",
            model="small",
        )

    entries = store.list_entries(limit=MAX_HISTORY_LIMIT + 200)
    assert len(entries) == MAX_HISTORY_LIMIT


def test_delete_and_clear(tmp_path):
    store = HistoryStore(tmp_path / "history.sqlite3")
    entry = store.add_entry(
        text="delete me",
        duration_ms=3,
        backend="faster-whisper",
        model="small",
    )
    store.add_entry(
        text="keep then clear",
        duration_ms=4,
        backend="faster-whisper",
        model="small",
    )

    assert store.delete_entry(entry["id"]) is True
    assert store.delete_entry(entry["id"]) is False
    cleared = store.clear()
    assert cleared == 1
    assert store.count_entries() == 0


def test_export_txt_and_csv(tmp_path):
    store = HistoryStore(tmp_path / "history.sqlite3")
    store.add_entry(
        text="hello export",
        duration_ms=55,
        backend="faster-whisper",
        model="small",
    )

    txt_path = store.export_txt(tmp_path / "out" / "history.txt")
    csv_path = store.export_csv(tmp_path / "out" / "history.csv")

    assert txt_path.exists()
    assert csv_path.exists()

    txt = txt_path.read_text(encoding="utf-8")
    csv = csv_path.read_text(encoding="utf-8")
    assert "hello export" in txt
    assert "hello export" in csv
    assert "created_at" in csv
