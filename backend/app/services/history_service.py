import sqlite3
import os
from pathlib import Path

from app.schemas.trip import TripPlan
from app.services import auth_service, memory_service
from app.services.history_migration import migrate_plan

DB_PATH = Path(os.getenv("HISTORY_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "trip_history.db")))

# Existing single-user rows are handed to this reserved account once user_id exists.
LEGACY_USER_ID = auth_service.LEGACY_USER_ID
LEGACY_DEMO_USER_ID = auth_service.ANONYMOUS_USER_ID


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 10,
                    destination TEXT NOT NULL,
                    days INTEGER NOT NULL,
                    budget INTEGER NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            if "user_id" not in _column_names(conn, "trip_history"):
                conn.execute(
                    f"ALTER TABLE trip_history ADD COLUMN user_id INTEGER NOT NULL DEFAULT {LEGACY_USER_ID}"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_trip_history_user ON trip_history(user_id, id DESC)"
            )
    finally:
        conn.close()

    memory_service.init_db()
    memory_service.seed_memory_from_history()


def save_plan(plan: TripPlan, user_id: int = LEGACY_USER_ID) -> int:
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO trip_history (user_id, destination, days, budget, plan_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(user_id), plan.destination, plan.days, plan.budget, plan.model_dump_json()),
            )
            return int(cursor.lastrowid)
    finally:
        conn.close()


def list_plans(user_id: int = LEGACY_USER_ID) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, destination, days, budget, created_at
            FROM trip_history
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (int(user_id),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_plan(plan_id: int, user_id: int = LEGACY_USER_ID) -> TripPlan | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT plan_json FROM trip_history WHERE id = ? AND user_id = ?",
            (int(plan_id), int(user_id)),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    plan = TripPlan.model_validate_json(row["plan_json"])
    return migrate_plan(plan)


def delete_plan(plan_id: int, user_id: int = LEGACY_USER_ID) -> bool:
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM trip_history WHERE id = ? AND user_id = ?",
                (int(plan_id), int(user_id)),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()
