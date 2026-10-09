"""Async plan-generation tasks with durable state and a local worker pool.

The public surface (create/get/cancel/stream) is intentionally storage-agnostic:
this SQLite implementation is the single-node default, and the same four calls
can be re-pointed at Redis + a separate worker process without touching routes.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from app.agents.orchestrator import plan_trip
from app.schemas.trip import TripPlan, TripRequest
from app.services import memory_service
from app.services.cancellation import TaskCancelled
from app.services.progress import reset_progress_callback, set_progress_callback

DB_PATH = Path(os.getenv("TASK_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "tasks.db")))

WORKER_COUNT = max(1, int(os.getenv("TASK_WORKER_COUNT", "2")))
MAX_RUNNING_PER_USER = max(1, int(os.getenv("TASK_MAX_RUNNING_PER_USER", "2")))
SUBMIT_WINDOW_SECONDS = max(1, int(os.getenv("TASK_SUBMIT_WINDOW_SECONDS", "3600")))
SUBMIT_MAX_PER_WINDOW = max(1, int(os.getenv("TASK_SUBMIT_MAX_PER_WINDOW", "30")))
POLL_INTERVAL_SECONDS = float(os.getenv("TASK_POLL_INTERVAL_SECONDS", "0.2"))
STALE_RUNNING_SECONDS = max(60, int(os.getenv("TASK_STALE_RUNNING_SECONDS", "900")))

TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")

_wake = threading.Event()
_stop = threading.Event()
_workers: list[threading.Thread] = []
_lock = threading.Lock()
_started = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plan_tasks (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress_stage TEXT NOT NULL DEFAULT '',
                    progress_message TEXT NOT NULL DEFAULT '',
                    request_json TEXT NOT NULL,
                    plan_json TEXT,
                    error TEXT NOT NULL DEFAULT '',
                    trace_id TEXT NOT NULL DEFAULT '',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_plan_tasks_user ON plan_tasks(user_id, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_plan_tasks_status ON plan_tasks(status, created_at)"
            )
    finally:
        conn.close()


def start_workers() -> None:
    global _started
    with _lock:
        if _started:
            return
        _stop.clear()
        for index in range(WORKER_COUNT):
            thread = threading.Thread(target=_worker_loop, name=f"plan-worker-{index}", daemon=True)
            thread.start()
            _workers.append(thread)
        _started = True


def stop_workers() -> None:
    global _started
    with _lock:
        _stop.set()
        _wake.set()
        _started = False


def _requeue_stale_tasks() -> None:
    """A killed worker leaves rows running forever; make them retryable."""
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                UPDATE plan_tasks
                SET status = 'queued', progress_message = '任务中断，已重新排队'
                WHERE status = 'running'
                  AND (started_at IS NULL OR started_at < datetime('now', 'localtime', ?))
                """,
                (f"-{STALE_RUNNING_SECONDS} seconds",),
            )
    finally:
        conn.close()


def create_task(user_id: int, req: TripRequest) -> dict:
    task_id = uuid.uuid4().hex
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO plan_tasks (id, user_id, request_json, progress_message)
                VALUES (?, ?, ?, ?)
                """,
                (task_id, int(user_id), req.model_dump_json(), "任务已提交，等待调度"),
            )
    finally:
        conn.close()
    _wake.set()
    return get_task(task_id, user_id) or {}


def submit_rate_limited(user_id: int) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM plan_tasks
            WHERE user_id = ? AND created_at >= datetime('now', 'localtime', ?)
            """,
            (int(user_id), f"-{SUBMIT_WINDOW_SECONDS} seconds"),
        ).fetchone()
    finally:
        conn.close()
    return int(row["c"] or 0) >= SUBMIT_MAX_PER_WINDOW


def count_running(user_id: int) -> int:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM plan_tasks WHERE user_id = ? AND status IN ('queued', 'running')",
            (int(user_id),),
        ).fetchone()
    finally:
        conn.close()
    return int(row["c"] or 0)


def _claim_task() -> dict | None:
    conn = _connect()
    try:
        with conn:
            row = conn.execute(
                """
                SELECT * FROM plan_tasks
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            cursor = conn.execute(
                """
                UPDATE plan_tasks
                SET status = 'running', started_at = datetime('now', 'localtime')
                WHERE id = ? AND status = 'queued'
                """,
                (row["id"],),
            )
            if cursor.rowcount == 0:
                return None
            return dict(row)
    finally:
        conn.close()


def _update_progress(task_id: str, message: str, stage: str = "") -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                UPDATE plan_tasks
                SET progress_message = ?, progress_stage = ?
                WHERE id = ? AND status = 'running'
                """,
                (message, stage, task_id),
            )
    finally:
        conn.close()


def _finish(task_id: str, status: str, plan: TripPlan | None = None, error: str = "", trace_id: str = "") -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                UPDATE plan_tasks
                SET status = ?, plan_json = ?, error = ?, trace_id = ?,
                    progress_message = ?, finished_at = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (
                    status,
                    plan.model_dump_json() if plan is not None else None,
                    error,
                    trace_id,
                    "已完成" if status == "succeeded" else ("已取消" if status == "cancelled" else error),
                    task_id,
                ),
            )
    finally:
        conn.close()


def _is_cancel_requested(task_id: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT cancel_requested, status FROM plan_tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    return bool(row and (row["cancel_requested"] or row["status"] == "cancelled"))


def cancel_task(task_id: str, user_id: int) -> bool:
    conn = _connect()
    try:
        with conn:
            row = conn.execute(
                "SELECT status FROM plan_tasks WHERE id = ? AND user_id = ?",
                (task_id, int(user_id)),
            ).fetchone()
            if row is None:
                return False
            if row["status"] in TERMINAL_STATUSES:
                return True
            conn.execute(
                """
                UPDATE plan_tasks
                SET cancel_requested = 1,
                    status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                    finished_at = CASE WHEN status = 'queued' THEN datetime('now', 'localtime') ELSE finished_at END,
                    progress_message = CASE WHEN status = 'queued' THEN '已取消' ELSE progress_message END
                WHERE id = ?
                """,
                (task_id,),
            )
    finally:
        conn.close()
    _wake.set()
    return True


def get_task(task_id: str, user_id: int | None = None) -> dict | None:
    conn = _connect()
    try:
        if user_id is None:
            row = conn.execute("SELECT * FROM plan_tasks WHERE id = ?", (task_id,)).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM plan_tasks WHERE id = ? AND user_id = ?",
                (task_id, int(user_id)),
            ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _serialise(dict(row))


def _serialise(row: dict) -> dict:
    plan = None
    if row.get("plan_json"):
        try:
            plan = TripPlan.model_validate_json(row["plan_json"]).model_dump()
        except Exception:
            plan = None
    return {
        "task_id": row["id"],
        "user_id": row["user_id"],
        "status": row["status"],
        "progress_stage": row["progress_stage"],
        "progress_message": row["progress_message"],
        "error": row["error"],
        "trace_id": row["trace_id"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "plan": plan,
    }


def list_tasks(user_id: int, limit: int = 20) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, status, progress_message, created_at, started_at, finished_at, error
            FROM plan_tasks
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(user_id), max(1, min(limit, 100))),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "task_id": row["id"],
            "status": row["status"],
            "progress_message": row["progress_message"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "error": row["error"],
        }
        for row in rows
    ]


def _run_task(task: dict) -> None:
    task_id = task["id"]
    user_id = int(task["user_id"])
    try:
        req = TripRequest.model_validate_json(task["request_json"])
    except Exception as exc:  # noqa: BLE001
        _finish(task_id, "failed", error=f"任务参数无法解析：{exc}")
        return

    def sink(message: str) -> None:
        _update_progress(task_id, message)

    token = set_progress_callback(sink)
    try:
        merged = memory_service.merge_memory_into_request(req, user_id)
        plan = plan_trip(
            merged,
            source="api_async",
            request_id=task_id,
            user_id=user_id,
            cancel_check=lambda: _is_cancel_requested(task_id),
        )
        if _is_cancel_requested(task_id):
            _finish(task_id, "cancelled")
            return
        _finish(task_id, "succeeded", plan=plan, trace_id=str(getattr(plan, "_trace_id", "") or ""))
    except TaskCancelled:
        _finish(task_id, "cancelled")
    except Exception as exc:  # noqa: BLE001
        _finish(task_id, "failed", error=_friendly_error(exc))
    finally:
        reset_progress_callback(token)
        _wake.set()



def _friendly_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()
    if "openai" in lower or "deepseek" in lower or "api error" in lower:
        return "AI 服务暂时不可用，请稍后重试"
    if message:
        return message
    return "服务暂时不可用，请稍后重试"


def _worker_loop() -> None:
    _requeue_stale_tasks()
    while not _stop.is_set():
        task = _claim_task()
        if task is None:
            _wake.wait(timeout=POLL_INTERVAL_SECONDS)
            _wake.clear()
            continue
        _run_task(task)

