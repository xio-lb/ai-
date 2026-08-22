import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.getenv("HISTORY_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "trip_history.db")))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL DEFAULT '新对话',
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
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


def create_session(title: str = "新对话") -> int:
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO chat_sessions (title) VALUES (?)",
                (title,),
            )
            return int(cursor.lastrowid)
    finally:
        conn.close()


def list_sessions() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) AS message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.updated_at DESC, s.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_session(session_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    return dict(row) if row else None


def get_messages(session_id: int) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT role, content, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def append_message(session_id: int, role: str, content: str) -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            conn.execute(
                "UPDATE chat_sessions SET updated_at = datetime('now', 'localtime') WHERE id = ?",
                (session_id,),
            )
    finally:
        conn.close()


def rename_session(session_id: int, title: str) -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "UPDATE chat_sessions SET title = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
                (title, session_id),
            )
    finally:
        conn.close()


def delete_session(session_id: int) -> bool:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "DELETE FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            cursor = conn.execute(
                "DELETE FROM chat_sessions WHERE id = ?",
                (session_id,),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()
