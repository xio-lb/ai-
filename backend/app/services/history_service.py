import sqlite3
import os
from pathlib import Path

from app.schemas.trip import TripPlan
from app.services import memory_service
from app.services.history_migration import migrate_plan

DB_PATH = Path(os.getenv("HISTORY_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "trip_history.db")))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    destination TEXT NOT NULL,
                    days INTEGER NOT NULL,
                    budget INTEGER NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
    finally:
        conn.close()

    memory_service.init_db()
    memory_service.seed_memory_from_history()


def save_plan(plan: TripPlan) -> int:
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO trip_history (destination, days, budget, plan_json)
                VALUES (?, ?, ?, ?)
                """,
                (plan.destination, plan.days, plan.budget, plan.model_dump_json()),
            )
            return int(cursor.lastrowid)
    finally:
        conn.close()


def list_plans() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, destination, days, budget, created_at
            FROM trip_history
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_plan(plan_id: int) -> TripPlan | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT plan_json FROM trip_history WHERE id = ?",
            (plan_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    plan = TripPlan.model_validate_json(row["plan_json"])
    return migrate_plan(plan)


def delete_plan(plan_id: int) -> bool:
    conn = _connect()
    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM trip_history WHERE id = ?",
                (plan_id,),
            )
            return cursor.rowcount > 0
    finally:
        conn.close()