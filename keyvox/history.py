"""SQLite-backed transcription history storage."""
from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

from .config import get_config_path

DEFAULT_DB_FILENAME = "history.sqlite3"
MAX_HISTORY_LIMIT = 1000


def resolve_history_db_path(config: Dict[str, Any]) -> Path:
    """Resolve history DB path from config or platform defaults."""
    configured = config.get("paths", {}).get("history_db", "")
    if isinstance(configured, str) and configured.strip():
        return Path(configured).expanduser()

    config_path = get_config_path()
    if config_path is not None:
        return config_path.parent / DEFAULT_DB_FILENAME
    return Path.cwd() / DEFAULT_DB_FILENAME


class HistoryStore:
    """Persist and query transcriptions in SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "HistoryStore":
        return cls(resolve_history_db_path(config))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    text TEXT NOT NULL,
                    duration_ms INTEGER,
                    backend TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ok'
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcriptions_created_at
                ON transcriptions(created_at DESC)
                """
            )
            conn.commit()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "created_at": row["created_at"],
            "text": row["text"],
            "duration_ms": row["duration_ms"],
            "backend": row["backend"],
            "model": row["model"],
            "status": row["status"],
        }

    def add_entry(
        self,
        *,
        text: str,
        duration_ms: int | None,
        backend: str,
        model: str,
        status: str = "ok",
    ) -> Dict[str, Any]:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO transcriptions (text, duration_ms, backend, model, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (text, duration_ms, backend, model, status),
            )
            row = conn.execute(
                """
                SELECT id, created_at, text, duration_ms, backend, model, status
                FROM transcriptions
                WHERE id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
            conn.commit()
        return self._row_to_dict(row)

    def list_entries(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str = "",
    ) -> List[Dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), MAX_HISTORY_LIMIT))
        bounded_offset = max(0, int(offset))
        like_search = f"%{search.strip()}%"

        sql = """
            SELECT id, created_at, text, duration_ms, backend, model, status
            FROM transcriptions
        """
        params: list[Any] = []
        if search.strip():
            sql += " WHERE text LIKE ?"
            params.append(like_search)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([bounded_limit, bounded_offset])

        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count_entries(self, *, search: str = "") -> int:
        sql = "SELECT COUNT(*) AS total FROM transcriptions"
        params: list[Any] = []
        if search.strip():
            sql += " WHERE text LIKE ?"
            params.append(f"%{search.strip()}%")
        with self._connection() as conn:
            row = conn.execute(sql, params).fetchone()
        return int(row["total"])

    def delete_entry(self, entry_id: int) -> bool:
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM transcriptions WHERE id = ?",
                (int(entry_id),),
            )
            conn.commit()
        return cursor.rowcount > 0

    def clear(self) -> int:
        with self._connection() as conn:
            count_row = conn.execute(
                "SELECT COUNT(*) AS total FROM transcriptions"
            ).fetchone()
            conn.execute("DELETE FROM transcriptions")
            conn.commit()
        return int(count_row["total"])

    def export_txt(self, output_path: Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, text, duration_ms, backend, model, status
                FROM transcriptions
                ORDER BY id ASC
                """
            ).fetchall()

        lines = []
        for row in rows:
            entry = self._row_to_dict(row)
            lines.append(
                f"[{entry['created_at']}] {entry['text']} "
                f"(backend={entry['backend']}, model={entry['model']}, "
                f"duration_ms={entry['duration_ms']})"
            )
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    def export_csv(self, output_path: Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        entries = self.list_entries(limit=MAX_HISTORY_LIMIT, offset=0, search="")
        entries.reverse()  # chronological export
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "id",
                    "created_at",
                    "text",
                    "duration_ms",
                    "backend",
                    "model",
                    "status",
                ],
            )
            writer.writeheader()
            for entry in entries:
                writer.writerow(entry)
        return output_path
