import json
import os
import sqlite3
from pathlib import Path

from app.schemas.trip import TripPlan, TripRequest
from app.services import auth_service

DB_PATH = Path(os.getenv("HISTORY_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "trip_history.db")))

LEGACY_USER_ID = auth_service.LEGACY_USER_ID
_VALID_PACES = ("compact", "standard", "relaxed")
_VALID_TRANSPORT = ("auto", "walking", "driving", "transit", "bicycling")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _default_memory() -> dict:
    return {
        "preferences": [],
        "visited_cities": [],
        "dietary_notes": "",
        "pace": "",
        "transport_mode": "",
        "hotel_budget": 0,
        "companions": 1,
        "updated_at": "",
    }


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            columns = _column_names(conn, "user_memory")
            if not columns:
                conn.execute(
                    """
                    CREATE TABLE user_memory (
                        user_id INTEGER PRIMARY KEY,
                        preferences_json TEXT NOT NULL DEFAULT '[]',
                        visited_cities_json TEXT NOT NULL DEFAULT '[]',
                        dietary_notes TEXT NOT NULL DEFAULT '',
                        pace TEXT NOT NULL DEFAULT '',
                        transport_mode TEXT NOT NULL DEFAULT '',
                        hotel_budget INTEGER NOT NULL DEFAULT 0,
                        companions INTEGER NOT NULL DEFAULT 1,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                    )
                    """
                )
            elif "user_id" not in columns:
                # Migrate the legacy single-row table (id CHECK (id = 1)) into a per-user table.
                conn.execute("ALTER TABLE user_memory RENAME TO user_memory_legacy")
                conn.execute(
                    """
                    CREATE TABLE user_memory (
                        user_id INTEGER PRIMARY KEY,
                        preferences_json TEXT NOT NULL DEFAULT '[]',
                        visited_cities_json TEXT NOT NULL DEFAULT '[]',
                        dietary_notes TEXT NOT NULL DEFAULT '',
                        pace TEXT NOT NULL DEFAULT '',
                        transport_mode TEXT NOT NULL DEFAULT '',
                        hotel_budget INTEGER NOT NULL DEFAULT 0,
                        companions INTEGER NOT NULL DEFAULT 1,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO user_memory (
                        user_id, preferences_json, visited_cities_json, dietary_notes,
                        pace, transport_mode, hotel_budget, companions, updated_at
                    )
                    SELECT ?, preferences_json, visited_cities_json, dietary_notes,
                           pace, transport_mode, hotel_budget, companions, updated_at
                    FROM user_memory_legacy
                    """,
                    (LEGACY_USER_ID,),
                )
                conn.execute("DROP TABLE user_memory_legacy")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_memory_user ON user_memory(user_id)"
            )
    finally:
        conn.close()


def _clean_string_list(values: list | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        item = str(value).strip()
        if item and item not in result:
            result.append(item)
    return result


def get_user_memory(user_id: int = LEGACY_USER_ID) -> dict:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM user_memory WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return _default_memory()

    return {
        "preferences": _clean_string_list(json.loads(row["preferences_json"] or "[]")),
        "visited_cities": _clean_string_list(json.loads(row["visited_cities_json"] or "[]")),
        "dietary_notes": row["dietary_notes"] or "",
        "pace": row["pace"] if row["pace"] in _VALID_PACES else "",
        "transport_mode": row["transport_mode"] if row["transport_mode"] in _VALID_TRANSPORT else "",
        "hotel_budget": int(row["hotel_budget"] or 0),
        "companions": int(row["companions"] or 1),
        "updated_at": row["updated_at"] or "",
    }


def save_user_memory(memory: dict, user_id: int = LEGACY_USER_ID) -> dict:
    normalized = _default_memory()
    normalized["preferences"] = _clean_string_list(memory.get("preferences"))
    normalized["visited_cities"] = _clean_string_list(memory.get("visited_cities"))
    normalized["dietary_notes"] = str(memory.get("dietary_notes") or "").strip()
    pace = str(memory.get("pace") or "")
    normalized["pace"] = pace if pace in _VALID_PACES else ""
    transport = str(memory.get("transport_mode") or "")
    normalized["transport_mode"] = transport if transport in _VALID_TRANSPORT else ""
    normalized["hotel_budget"] = max(0, int(memory.get("hotel_budget") or 0))
    normalized["companions"] = max(1, int(memory.get("companions") or 1))

    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO user_memory (
                    user_id, preferences_json, visited_cities_json, dietary_notes,
                    pace, transport_mode, hotel_budget, companions, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
                """,
                (
                    int(user_id),
                    json.dumps(normalized["preferences"], ensure_ascii=False),
                    json.dumps(normalized["visited_cities"], ensure_ascii=False),
                    normalized["dietary_notes"],
                    normalized["pace"],
                    normalized["transport_mode"],
                    normalized["hotel_budget"],
                    normalized["companions"],
                ),
            )
    finally:
        conn.close()

    return get_user_memory(user_id)


def _merge_plan_into(memory: dict, plan: TripPlan) -> None:
    user_preferences = getattr(plan, "user_preferences", None) or []
    for preference in user_preferences:
        item = str(preference).strip()
        if item and item not in memory["preferences"]:
            memory["preferences"].append(item)

    if plan.destination and plan.destination not in memory["visited_cities"]:
        memory["visited_cities"].append(plan.destination)

    if getattr(plan, "dietary_notes", ""):
        memory["dietary_notes"] = plan.dietary_notes
    if plan.variant_pace in _VALID_PACES:
        memory["pace"] = plan.variant_pace
    if plan.transport_mode in _VALID_TRANSPORT:
        memory["transport_mode"] = plan.transport_mode
    if getattr(plan, "hotel_budget", 0):
        memory["hotel_budget"] = plan.hotel_budget
    if getattr(plan, "companions", 1):
        memory["companions"] = plan.companions


def update_memory_from_plan(plan: TripPlan, user_id: int = LEGACY_USER_ID) -> dict:
    memory = get_user_memory(user_id)
    _merge_plan_into(memory, plan)
    return save_user_memory(memory, user_id)


def seed_memory_from_history(user_id: int = LEGACY_USER_ID) -> None:
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT user_id FROM user_memory WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        if existing is not None:
            return
        history_columns = _column_names(conn, "trip_history")
        if not history_columns:
            rows = []
        elif "user_id" in history_columns:
            rows = conn.execute(
                "SELECT plan_json FROM trip_history WHERE user_id = ?",
                (int(user_id),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT plan_json FROM trip_history").fetchall()
    finally:
        conn.close()

    memory = _default_memory()
    for row in rows:
        try:
            plan = TripPlan.model_validate_json(row["plan_json"])
        except Exception:
            continue
        _merge_plan_into(memory, plan)

    if memory["preferences"] or memory["visited_cities"]:
        save_user_memory(memory, user_id)


def merge_memory_into_request(req: TripRequest, user_id: int = LEGACY_USER_ID) -> TripRequest:
    memory = get_user_memory(user_id)
    preferences = _clean_string_list(req.preferences)
    for preference in memory["preferences"]:
        if preference not in preferences:
            preferences.append(preference)

    updates: dict = {"preferences": preferences}

    if not req.dietary_notes and memory["dietary_notes"]:
        updates["dietary_notes"] = memory["dietary_notes"]
    if (not req.pace or req.pace == "standard") and memory["pace"]:
        updates["pace"] = memory["pace"]
    if (not req.transport_mode or req.transport_mode == "auto") and memory["transport_mode"]:
        updates["transport_mode"] = memory["transport_mode"]
    if not req.hotel_budget and memory["hotel_budget"]:
        updates["hotel_budget"] = memory["hotel_budget"]
    if req.companions <= 1 and memory["companions"] > 1:
        updates["companions"] = memory["companions"]

    return req.model_copy(update=updates)
