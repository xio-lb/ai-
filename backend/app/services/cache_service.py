"""Persistent SQLite cache for external API results."""
import os

import json
import sqlite3
import threading
import time
from pathlib import Path

DB_PATH = Path(os.getenv("AMAP_CACHE_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "amap_cache.db")))

_init_lock = threading.Lock()
_initialized_path: Path | None = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    global _initialized_path
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS amap_cache (
                    namespace TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    PRIMARY KEY (namespace, cache_key)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_amap_cache_expires ON amap_cache(expires_at)"
            )
            conn.execute(
                "DELETE FROM amap_cache WHERE expires_at <= ?",
                (int(time.time()),),
            )
    finally:
        conn.close()
    _initialized_path = DB_PATH


def _ensure_initialized() -> None:
    global _initialized_path
    if _initialized_path == DB_PATH:
        return
    with _init_lock:
        if _initialized_path == DB_PATH:
            return
        init_db()


def _trace_cache(namespace: str, hit: bool) -> None:
    try:
        from app.services.observability import record_cache_event

        record_cache_event(namespace, hit, layer="persistent")
    except Exception:
        return


def get_cached(namespace: str, cache_key: str):
    _ensure_initialized()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload, expires_at FROM amap_cache WHERE namespace = ? AND cache_key = ?",
            (namespace, cache_key),
        ).fetchone()
        if row is None:
            _trace_cache(namespace, False)
            return None
        if row["expires_at"] <= int(time.time()):
            with conn:
                conn.execute(
                    "DELETE FROM amap_cache WHERE namespace = ? AND cache_key = ?",
                    (namespace, cache_key),
                )
            _trace_cache(namespace, False)
            return None
        try:
            value = json.loads(row["payload"])
            _trace_cache(namespace, True)
            return value
        except (TypeError, ValueError):
            with conn:
                conn.execute(
                    "DELETE FROM amap_cache WHERE namespace = ? AND cache_key = ?",
                    (namespace, cache_key),
                )
            _trace_cache(namespace, True)
            return None
    finally:
        conn.close()


def set_cached(namespace: str, cache_key: str, value, ttl_seconds: int) -> None:
    _ensure_initialized()
    now = int(time.time())
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO amap_cache (
                    namespace, cache_key, payload, created_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    namespace,
                    cache_key,
                    payload,
                    now,
                    now + max(0, int(ttl_seconds)),
                ),
            )
    finally:
        conn.close()


def clear(namespace: str | None = None) -> int:
    _ensure_initialized()
    conn = _connect()
    try:
        with conn:
            if namespace is None:
                cursor = conn.execute("DELETE FROM amap_cache")
            else:
                cursor = conn.execute(
                    "DELETE FROM amap_cache WHERE namespace = ?",
                    (namespace,),
                )
        return cursor.rowcount
    finally:
        conn.close()


def stats() -> dict:
    _ensure_initialized()
    conn = _connect()
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM amap_cache"
        ).fetchone()["c"]
        expired = conn.execute(
            "SELECT COUNT(*) AS c FROM amap_cache WHERE expires_at <= ?",
            (int(time.time()),),
        ).fetchone()["c"]
        return {"total": total, "expired": expired}
    finally:
        conn.close()
