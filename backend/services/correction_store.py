from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


_DEFAULT_DB_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "corrections.db"
)


class CorrectionStore:
    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or _DEFAULT_DB_PATH
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS corrections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    original_status TEXT NOT NULL,
                    corrected_status TEXT NOT NULL,
                    admin_id TEXT,
                    admin_email TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(conversation_id, url)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def save_correction(
        self,
        conversation_id: str,
        message_id: str,
        url: str,
        original_status: str,
        corrected_status: str,
        admin_id: Optional[str],
        admin_email: Optional[str],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO corrections
                    (conversation_id, message_id, url, original_status,
                     corrected_status, admin_id, admin_email)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id, url) DO UPDATE SET
                    message_id = excluded.message_id,
                    corrected_status = excluded.corrected_status,
                    original_status = excluded.original_status,
                    admin_id = excluded.admin_id,
                    admin_email = excluded.admin_email,
                    created_at = datetime('now')
                """,
                (
                    conversation_id,
                    message_id,
                    url,
                    original_status,
                    corrected_status,
                    admin_id,
                    admin_email,
                ),
            )

    def get_corrections(self, conversation_id: str) -> dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT url, corrected_status FROM corrections WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
        return {url: status for url, status in rows}

    def delete_correction(self, conversation_id: str, url: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM corrections WHERE conversation_id = ? AND url = ?",
                (conversation_id, url),
            )

    def list_corrections(
        self,
        conversation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        with self._connect() as conn:
            if conversation_id:
                rows = conn.execute(
                    """
                    SELECT conversation_id, message_id, url, original_status,
                           corrected_status, admin_id, admin_email, created_at
                    FROM corrections
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (conversation_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT conversation_id, message_id, url, original_status,
                           corrected_status, admin_id, admin_email, created_at
                    FROM corrections
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        columns = [
            "conversation_id", "message_id", "url", "original_status",
            "corrected_status", "admin_id", "admin_email", "created_at",
        ]
        return [dict(zip(columns, row)) for row in rows]
