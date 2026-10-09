import os
import sqlite3
from pathlib import Path

from app.services import auth_service

DB_PATH = Path(os.getenv("HISTORY_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "trip_history.db")))

LEGACY_USER_ID = auth_service.LEGACY_USER_ID


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 10,
                    title TEXT NOT NULL DEFAULT '新对话',
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            if "user_id" not in _column_names(conn, "chat_sessions"):
                conn.execute(
                    f"ALTER TABLE chat_sessions ADD COLUMN user_id INTEGER NOT NULL DEFAULT {LEGACY_USER_ID}"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_user ON chat_sessions(user_id, updated_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id)"
            )
    finally:
        conn.close()


def create_session(title: str = "新对话", user_id: int = LEGACY_USER_ID) -> int:
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO chat_sessions (user_id, title) VALUES (?, ?)",
                (int(user_id), title),
            )
            return int(cursor.lastrowid)
    finally:
        conn.close()


def list_sessions(user_id: int = LEGACY_USER_ID) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) AS message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            WHERE s.user_id = ?
            GROUP BY s.id
            ORDER BY s.updated_at DESC, s.id DESC
            """,
            (int(user_id),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_session(session_id: int, user_id: int = LEGACY_USER_ID) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = ? AND user_id = ?",
            (int(session_id), int(user_id)),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_messages(session_id: int, user_id: int = LEGACY_USER_ID) -> list[dict]:
    if get_session(session_id, user_id) is None:
        return []
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT role, content, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (int(session_id),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def append_message(session_id: int, role: str, content: str, user_id: int = LEGACY_USER_ID) -> bool:
    if get_session(session_id, user_id) is None:
        return False
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                (int(session_id), role, content),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = datetime('now', 'localtime') WHERE id = ?",
                (int(session_id),),
            )
        return True
    finally:
        conn.close()


def rename_session(session_id: int, title: str, user_id: int = LEGACY_USER_ID) -> bool:
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                """
                UPDATE chat_sessions
                SET title = ?, updated_at = datetime('now', 'localtime')
                WHERE id = ? AND user_id = ?
                """,
                (title, int(session_id), int(user_id)),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()


def delete_session(session_id: int, user_id: int = LEGACY_USER_ID) -> bool:
    if get_session(session_id, user_id) is None:
        return False
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (int(session_id),),
            )
            cursor = conn.execute(
                "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
                (int(session_id), int(user_id)),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()
