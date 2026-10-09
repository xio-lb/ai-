"""Lightweight tracing and metrics for trip generation runs.

The project intentionally keeps this layer dependency-light so downstream
services can record metrics without threading a trace object through every
function signature. A trace is kept in a ContextVar, which means the API,
LangGraph worker thread, LLM client, cache and Amap client can all contribute
events to the same run.

The storage backend is SQLite for the current single-instance deployment.
The public API (trace_generation, summary, list_traces, get_trace) is designed
to be replaceable by PostgreSQL/Redis later without changing call sites.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator

from dotenv import load_dotenv

from app.schemas.trip import TripPlan, TripRequest

load_dotenv()

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = Path(os.getenv("TRACE_DB_PATH", str(ROOT / "observability.db")))

_current_trace: ContextVar["TraceContext | None"] = ContextVar(
    "current_trace", default=None
)
_init_lock = threading.Lock()
_initialized_path: Path | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def current_trace() -> "TraceContext | None":
    """Return the trace attached to the current execution context."""

    return _current_trace.get()


def _with_trace(method: str, *args: Any, **kwargs: Any) -> None:
    """Fail-open wrapper around trace mutation methods."""

    trace = _current_trace.get()
    if trace is None:
        return
    try:
        getattr(trace, method)(*args, **kwargs)
    except Exception:
        return


class TraceContext:
    """Mutable state for one generation run."""

    def __init__(
        self,
        source: str,
        request: TripRequest | None = None,
        request_id: str | None = None,
        variant_theme: str = "",
    ) -> None:
        self.trace_id = uuid.uuid4().hex
        self.request_id = request_id or self.trace_id
        self.source = source
        self.variant_theme = variant_theme or (
            getattr(request, "variant_theme", "") if request else ""
        )
        self.destination = getattr(request, "destination", "") if request else ""
        self.days = _safe_int(getattr(request, "days", 0) if request else 0)
        self.budget = _safe_int(getattr(request, "budget", 0) if request else 0)
        self.pace = getattr(request, "pace", "") if request else ""
        self.started_at = _now_iso()
        self.ended_at: str | None = None
        self._started_perf = time.perf_counter()
        self.duration_ms = 0.0
        self.status = "running"
        self.error = ""

        self.nodes: list[dict[str, Any]] = []
        self.llm_calls: list[dict[str, Any]] = []
        self.external_calls: list[dict[str, Any]] = []
        self.cache_events: list[dict[str, Any]] = []
        self.retries: list[dict[str, Any]] = []
        self.quality_report: dict[str, Any] = {}
        self.budget_report: dict[str, Any] = {}
        self.route_issues: list[str] = []
        self.route_checked = False
        self.plan_summary: dict[str, Any] = {}
        self._lock = threading.Lock()

    def record_node(
        self, name: str, duration_ms: float, status: str = "success", error: str = ""
    ) -> None:
        with self._lock:
            self.nodes.append(
                {
                    "name": name,
                    "duration_ms": round(float(duration_ms), 2),
                    "status": status,
                    "error": error,
                }
            )

    def record_llm_call(
        self,
        name: str,
        model: str,
        prompt_hash: str,
        prompt_version: str,
        duration_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        estimated_cost: float = 0.0,
        success: bool = True,
        error: str = "",
    ) -> None:
        with self._lock:
            self.llm_calls.append(
                {
                    "name": name,
                    "model": model,
                    "prompt_hash": prompt_hash,
                    "prompt_version": prompt_version,
                    "duration_ms": round(float(duration_ms), 2),
                    "prompt_tokens": _safe_int(prompt_tokens),
                    "completion_tokens": _safe_int(completion_tokens),
                    "total_tokens": _safe_int(total_tokens),
                    "estimated_cost": round(float(estimated_cost or 0.0), 6),
                    "success": bool(success),
                    "error": error,
                }
            )

    def record_external_call(
        self,
        service: str,
        operation: str,
        duration_ms: float,
        success: bool = True,
        error: str = "",
        cache_hit: bool | None = None,
    ) -> None:
        with self._lock:
            self.external_calls.append(
                {
                    "service": service,
                    "operation": operation,
                    "duration_ms": round(float(duration_ms), 2),
                    "success": bool(success),
                    "error": error,
                    "cache_hit": cache_hit,
                }
            )

    def record_cache_event(self, namespace: str, hit: bool, layer: str = "persistent") -> None:
        with self._lock:
            self.cache_events.append(
                {
                    "namespace": namespace,
                    "hit": bool(hit),
                    "layer": layer,
                }
            )

    def record_retry(self, stage: str, attempt: int, reason: str = "") -> None:
        with self._lock:
            self.retries.append(
                {
                    "stage": stage,
                    "attempt": _safe_int(attempt),
                    "reason": reason[:500],
                }
            )

    def record_quality(self, report: dict[str, Any] | None) -> None:
        if not report:
            return
        with self._lock:
            self.quality_report = dict(report)

    def record_budget(self, report: Any) -> None:
        if report is None:
            return
        if hasattr(report, "model_dump"):
            report = report.model_dump()
        with self._lock:
            self.budget_report = dict(report)

    def record_route(self, issues: list[str] | None) -> None:
        with self._lock:
            self.route_checked = True
            self.route_issues = list(issues or [])

    def attach_plan(self, plan: TripPlan | None) -> None:
        if plan is None:
            return
        spots = sum(len(day.spots) for day in plan.daily_plans)
        foods = sum(len(day.foods) for day in plan.daily_plans)
        quality = plan.quality_report or {}
        issues = list(quality.get("issues") or [])
        with self._lock:
            self.plan_summary = {
                "destination": plan.destination,
                "days": plan.days,
                "budget": plan.budget,
                "total_cost": plan.total_cost,
                "spots": spots,
                "foods": foods,
                "hotels": len(plan.hotels),
                "route_legs": len(plan.route_legs),
                "quality_issue_count": len(issues),
                "quality_issues": issues[:10],
            }
            if quality:
                self.quality_report = dict(quality)

    def finalize(self, status: str | None = None, error: str = "") -> None:
        with self._lock:
            if self.status != "running":
                return
            self.status = status or "success"
            self.error = error[:1000]
            self.ended_at = _now_iso()
            self.duration_ms = _elapsed_ms(self._started_perf)

    def _derived(self) -> dict[str, Any]:
        llm_tokens = sum(_safe_int(call.get("total_tokens")) for call in self.llm_calls)
        estimated_cost = sum(float(call.get("estimated_cost") or 0) for call in self.llm_calls)
        cache_lookups = len(self.cache_events)
        cache_hits = sum(1 for event in self.cache_events if event.get("hit"))
        amap_calls = sum(
            1 for call in self.external_calls if call.get("service") == "amap"
        )
        quality_issues = list(self.quality_report.get("issues") or [])
        invalid_poi_count = _count_invalid_poi_issues(quality_issues)
        spots = _safe_int(self.plan_summary.get("spots"), 0)
        return {
            "success": self.status == "success",
            "quality_passed": self.quality_report.get("passed")
            if self.quality_report
            else None,
            "route_closed": (not self.route_issues) if self.route_checked else None,
            "budget_compliant": self.budget_report.get("within_budget")
            if self.budget_report
            else None,
            "invalid_poi_count": invalid_poi_count,
            "invalid_poi_rate": round(invalid_poi_count / spots, 4) if spots else 0.0,
            "quality_issue_count": len(quality_issues),
            "llm_call_count": len(self.llm_calls),
            "llm_tokens": llm_tokens,
            "estimated_cost": round(estimated_cost, 6),
            "amap_calls": amap_calls,
            "cache_hits": cache_hits,
            "cache_lookups": cache_lookups,
            "cache_hit_rate": round(cache_hits / cache_lookups, 4)
            if cache_lookups
            else 0.0,
            "retry_count": len(self.retries),
            "node_count": len(self.nodes),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = {
                "trace_id": self.trace_id,
                "request_id": self.request_id,
                "source": self.source,
                "variant_theme": self.variant_theme,
                "status": self.status,
                "error": self.error,
                "destination": self.destination,
                "days": self.days,
                "budget": self.budget,
                "pace": self.pace,
                "started_at": self.started_at,
                "ended_at": self.ended_at or "",
                "duration_ms": self.duration_ms,
                "nodes": list(self.nodes),
                "llm_calls": list(self.llm_calls),
                "external_calls": list(self.external_calls),
                "cache_events": list(self.cache_events),
                "retries": list(self.retries),
                "quality_report": dict(self.quality_report),
                "budget_report": dict(self.budget_report),
                "route_issues": list(self.route_issues),
                "route_checked": self.route_checked,
                "plan_summary": dict(self.plan_summary),
            }
            data.update(self._derived())
            return data


def _count_invalid_poi_issues(issues: list[str]) -> int:
    markers = (
        "不在候选清单",
        "坐标不可用",
        "空景点名称",
        "空餐厅名称",
    )
    return sum(1 for issue in issues if any(marker in issue for marker in markers))


def record_node(name: str, duration_ms: float, status: str = "success", error: str = "") -> None:
    _with_trace("record_node", name, duration_ms, status, error)


def record_llm_call(
    name: str,
    model: str,
    prompt_hash: str,
    prompt_version: str,
    duration_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    estimated_cost: float = 0.0,
    success: bool = True,
    error: str = "",
) -> None:
    _with_trace(
        "record_llm_call",
        name,
        model,
        prompt_hash,
        prompt_version,
        duration_ms,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        estimated_cost,
        success,
        error,
    )


def record_external_call(
    service: str,
    operation: str,
    duration_ms: float,
    success: bool = True,
    error: str = "",
    cache_hit: bool | None = None,
) -> None:
    _with_trace(
        "record_external_call",
        service,
        operation,
        duration_ms,
        success,
        error,
        cache_hit,
    )


def record_cache_event(namespace: str, hit: bool, layer: str = "persistent") -> None:
    _with_trace("record_cache_event", namespace, hit, layer)


def record_retry(stage: str, attempt: int, reason: str = "") -> None:
    _with_trace("record_retry", stage, attempt, reason)


def record_quality(report: dict[str, Any] | None) -> None:
    _with_trace("record_quality", report)


def record_budget(report: Any) -> None:
    _with_trace("record_budget", report)


def record_route(issues: list[str] | None) -> None:
    _with_trace("record_route", issues)


@contextmanager
def trace_generation(
    source: str,
    request: TripRequest | None = None,
    request_id: str | None = None,
    variant_theme: str = "",
) -> Iterator[TraceContext]:
    """Create or reuse a trace for a generation run.

    Nested calls reuse the active trace. The outermost context manager owns
    persistence, so variant generation and evaluation do not write duplicate
    partial traces.
    """

    existing = _current_trace.get()
    if existing is not None:
        yield existing
        return

    trace = TraceContext(
        source=source,
        request=request,
        request_id=request_id,
        variant_theme=variant_theme,
    )
    token = _current_trace.set(trace)
    try:
        yield trace
    except Exception as exc:
        trace.finalize(status="failure", error=str(exc))
        _safe_save(trace)
        raise
    else:
        if trace.status == "running":
            trace.finalize(status="success")
        _safe_save(trace)
    finally:
        _current_trace.reset(token)


@contextmanager
def external_call(service: str, operation: str) -> Iterator[None]:
    """Time one external API call and record success or failure."""

    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        record_external_call(service, operation, _elapsed_ms(started), False, str(exc))
        raise
    else:
        record_external_call(service, operation, _elapsed_ms(started), True)


def instrument_node(
    name: str, fn: Callable[[dict[str, Any]], Any]
) -> Callable[[dict[str, Any]], Any]:
    """Wrap a LangGraph node so every attempt contributes a timing event."""

    @wraps(fn)
    def wrapper(state: dict[str, Any]) -> Any:
        started = time.perf_counter()
        try:
            result = fn(state)
        except Exception as exc:
            record_node(name, _elapsed_ms(started), "error", str(exc))
            raise
        record_node(name, _elapsed_ms(started), "success")
        return result

    return wrapper


def _safe_save(trace: TraceContext) -> None:
    try:
        save_trace(trace)
    except Exception:
        return


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    global _initialized_path
    if _initialized_path == DB_PATH:
        return
    with _init_lock:
        if _initialized_path == DB_PATH:
            return
        conn = _connect()
        try:
            with conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS trace_runs (
                        trace_id TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        status TEXT NOT NULL,
                        destination TEXT NOT NULL DEFAULT '',
                        days INTEGER NOT NULL DEFAULT 0,
                        budget INTEGER NOT NULL DEFAULT 0,
                        pace TEXT NOT NULL DEFAULT '',
                        started_at TEXT NOT NULL,
                        ended_at TEXT NOT NULL DEFAULT '',
                        duration_ms REAL NOT NULL DEFAULT 0,
                        success INTEGER NOT NULL DEFAULT 0,
                        quality_passed INTEGER,
                        route_closed INTEGER,
                        budget_compliant INTEGER,
                        invalid_poi_count INTEGER NOT NULL DEFAULT 0,
                        llm_tokens INTEGER NOT NULL DEFAULT 0,
                        estimated_cost REAL NOT NULL DEFAULT 0,
                        amap_calls INTEGER NOT NULL DEFAULT 0,
                        cache_hits INTEGER NOT NULL DEFAULT 0,
                        cache_lookups INTEGER NOT NULL DEFAULT 0,
                        retry_count INTEGER NOT NULL DEFAULT 0,
                        error TEXT NOT NULL DEFAULT '',
                        payload TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_started ON trace_runs(started_at)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_request ON trace_runs(request_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_trace_status ON trace_runs(status)"
                )
        finally:
            conn.close()
        _initialized_path = DB_PATH


def _ensure_initialized() -> None:
    if _initialized_path != DB_PATH:
        init_db()


def save_trace(trace: TraceContext) -> None:
    _ensure_initialized()
    data = trace.snapshot()
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trace_runs (
                    trace_id, request_id, source, status, destination, days, budget,
                    pace, started_at, ended_at, duration_ms, success, quality_passed,
                    route_closed, budget_compliant, invalid_poi_count, llm_tokens,
                    estimated_cost, amap_calls, cache_hits, cache_lookups, retry_count,
                    error, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["trace_id"],
                    data["request_id"],
                    data["source"],
                    data["status"],
                    data["destination"],
                    data["days"],
                    data["budget"],
                    data["pace"],
                    data["started_at"],
                    data["ended_at"],
                    data["duration_ms"],
                    1 if data["success"] else 0,
                    _optional_bool(data["quality_passed"]),
                    _optional_bool(data["route_closed"]),
                    _optional_bool(data["budget_compliant"]),
                    data["invalid_poi_count"],
                    data["llm_tokens"],
                    data["estimated_cost"],
                    data["amap_calls"],
                    data["cache_hits"],
                    data["cache_lookups"],
                    data["retry_count"],
                    data["error"],
                    json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                ),
            )
    finally:
        conn.close()


def _optional_bool(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def fetch_records(days: int = 30, limit: int = 5000) -> list[dict[str, Any]]:
    _ensure_initialized()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))).isoformat(
        timespec="seconds"
    )
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT payload FROM trace_runs
            WHERE started_at >= ?
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (cutoff, max(1, int(limit))),
        ).fetchall()
    finally:
        conn.close()
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            records.append(json.loads(row["payload"]))
        except (TypeError, ValueError):
            continue
    return records


def list_traces(days: int = 30, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    records = fetch_records(days=days, limit=5000)
    return records[max(0, offset) : max(0, offset) + max(1, limit)]


def get_trace(trace_id: str) -> dict[str, Any] | None:
    _ensure_initialized()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT payload FROM trace_runs WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        return json.loads(row["payload"])
    except (TypeError, ValueError):
        return None


def _rate(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 4)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (len(ordered) - 1) * p
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(ordered[lower], 2)
    result = ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)
    return round(result, 2)


def aggregate_records(
    records: list[dict[str, Any]], window_days: int = 30
) -> dict[str, Any]:
    total = len(records)
    successes = [record for record in records if record.get("success")]
    durations = [float(record.get("duration_ms") or 0) for record in records]
    quality_checked = [r for r in records if r.get("quality_passed") is not None]
    route_checked = [r for r in records if r.get("route_closed") is not None]
    budget_checked = [r for r in records if r.get("budget_compliant") is not None]
    cache_lookups = sum(_safe_int(r.get("cache_lookups")) for r in records)
    cache_hits = sum(_safe_int(r.get("cache_hits")) for r in records)
    total_tokens = sum(_safe_int(r.get("llm_tokens")) for r in records)
    total_cost = sum(float(r.get("estimated_cost") or 0) for r in records)
    total_amap_calls = sum(_safe_int(r.get("amap_calls")) for r in records)
    total_retries = sum(_safe_int(r.get("retry_count")) for r in records)
    total_invalid_pois = sum(_safe_int(r.get("invalid_poi_count")) for r in records)
    total_spots = sum(
        _safe_int((r.get("plan_summary") or {}).get("spots")) for r in records
    )

    node_values: dict[str, list[float]] = {}
    for record in records:
        for node in record.get("nodes") or []:
            name = str(node.get("name") or "unknown")
            node_values.setdefault(name, []).append(float(node.get("duration_ms") or 0))

    node_stats = {
        name: {
            "count": len(values),
            "avg_ms": round(sum(values) / len(values), 2) if values else None,
            "p95_ms": percentile(values, 0.95),
            "max_ms": round(max(values), 2) if values else None,
        }
        for name, values in sorted(node_values.items())
    }

    error_counter = Counter(
        str(record.get("error") or "").strip()
        for record in records
        if str(record.get("error") or "").strip()
    )
    top_errors = [
        {"message": message, "count": count}
        for message, count in error_counter.most_common(10)
    ]

    return {
        "generated_at": _now_iso(),
        "window_days": window_days,
        "totals": {
            "runs": total,
            "success": len(successes),
            "failure": total - len(successes),
            "unique_requests": len(
                {str(r.get("request_id") or r.get("trace_id")) for r in records}
            ),
        },
        "rates": {
            "success_rate": _rate(len(successes), total),
            "quality_pass_rate": _rate(
                sum(1 for r in quality_checked if r.get("quality_passed")),
                len(quality_checked),
            ),
            "route_closure_rate": _rate(
                sum(1 for r in route_checked if r.get("route_closed")),
                len(route_checked),
            ),
            "budget_compliance_rate": _rate(
                sum(1 for r in budget_checked if r.get("budget_compliant")),
                len(budget_checked),
            ),
            "invalid_poi_run_rate": _rate(
                sum(1 for r in records if _safe_int(r.get("invalid_poi_count")) > 0),
                total,
            ),
            "cache_hit_rate": _rate(cache_hits, cache_lookups),
        },
        "latency_ms": {
            "avg": round(sum(durations) / len(durations), 2) if durations else None,
            "p50": percentile(durations, 0.5),
            "p95": percentile(durations, 0.95),
            "min": round(min(durations), 2) if durations else None,
            "max": round(max(durations), 2) if durations else None,
        },
        "tokens": {
            "total": total_tokens,
            "avg_per_run": round(total_tokens / total, 2) if total else None,
            "avg_per_success": round(total_tokens / len(successes), 2)
            if successes
            else None,
        },
        "cost": {
            "currency": "CNY",
            "total": round(total_cost, 6),
            "avg_per_run": round(total_cost / total, 6) if total else None,
            "configured": total_cost > 0,
        },
        "external": {
            "amap_calls_total": total_amap_calls,
            "amap_calls_avg": round(total_amap_calls / total, 2) if total else None,
            "cache_hits": cache_hits,
            "cache_lookups": cache_lookups,
        },
        "retries": {
            "total": total_retries,
            "avg_per_run": round(total_retries / total, 2) if total else None,
        },
        "invalid_poi": {
            "total": total_invalid_pois,
            "per_run": round(total_invalid_pois / total, 2) if total else None,
            "per_planned_spot": _rate(total_invalid_pois, total_spots),
        },
        "nodes": node_stats,
        "top_errors": top_errors,
    }


def summary(days: int = 30, limit: int = 5000) -> dict[str, Any]:
    return aggregate_records(fetch_records(days=days, limit=limit), window_days=days)


def prometheus_text(days: int = 30) -> str:
    data = summary(days=days)
    totals = data["totals"]
    rates = data["rates"]
    latency = data["latency_ms"]
    tokens = data["tokens"]
    cost = data["cost"]
    external = data["external"]
    lines = [
        "# HELP travel_planner_runs_total Total generation runs.",
        "# TYPE travel_planner_runs_total counter",
        f'travel_planner_runs_total{{status="success"}} {totals["success"]}',
        f'travel_planner_runs_total{{status="failure"}} {totals["failure"]}',
        "# HELP travel_planner_success_rate Successful runs divided by total runs.",
        "# TYPE travel_planner_success_rate gauge",
        f"travel_planner_success_rate {_metric_value(rates['success_rate'])}",
        "# HELP travel_planner_quality_pass_rate Quality checks passed divided by checked runs.",
        "# TYPE travel_planner_quality_pass_rate gauge",
        f"travel_planner_quality_pass_rate {_metric_value(rates['quality_pass_rate'])}",
        "# HELP travel_planner_route_closure_rate Route closure checks passed divided by checked runs.",
        "# TYPE travel_planner_route_closure_rate gauge",
        f"travel_planner_route_closure_rate {_metric_value(rates['route_closure_rate'])}",
        "# HELP travel_planner_budget_compliance_rate Budget checks passed divided by checked runs.",
        "# TYPE travel_planner_budget_compliance_rate gauge",
        f"travel_planner_budget_compliance_rate {_metric_value(rates['budget_compliance_rate'])}",
        "# HELP travel_planner_generation_duration_ms End-to-end generation duration.",
        "# TYPE travel_planner_generation_duration_ms gauge",
        f'travel_planner_generation_duration_ms{{quantile="0.5"}} {_metric_value(latency["p50"])}',
        f'travel_planner_generation_duration_ms{{quantile="0.95"}} {_metric_value(latency["p95"])}',
        "# HELP travel_planner_llm_tokens_total Total LLM tokens recorded.",
        "# TYPE travel_planner_llm_tokens_total counter",
        f"travel_planner_llm_tokens_total {tokens['total']}",
        "# HELP travel_planner_estimated_cost_cny_total Estimated LLM cost in CNY.",
        "# TYPE travel_planner_estimated_cost_cny_total counter",
        f"travel_planner_estimated_cost_cny_total {cost['total']}",
        "# HELP travel_planner_amap_calls_total Total Amap HTTP attempts.",
        "# TYPE travel_planner_amap_calls_total counter",
        f"travel_planner_amap_calls_total {external['amap_calls_total']}",
        "# HELP travel_planner_cache_hit_rate Persistent and memory cache hit rate.",
        "# TYPE travel_planner_cache_hit_rate gauge",
        f"travel_planner_cache_hit_rate {_metric_value(rates['cache_hit_rate'])}",
    ]
    for name, stats in data["nodes"].items():
        safe_name = _prometheus_label(name)
        lines.append(
            f'travel_planner_node_duration_ms{{node="{safe_name}",quantile="0.95"}} '
            f"{_metric_value(stats['p95_ms'])}"
        )
    lines.append("")
    return "\n".join(lines)


def _metric_value(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _prometheus_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def reset_for_tests() -> None:
    """Reset module-level cache when tests point DB_PATH at a temporary file."""

    global _initialized_path
    _initialized_path = None
