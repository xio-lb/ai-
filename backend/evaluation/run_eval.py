"""Run a fixed offline evaluation set against the real generation pipeline.

Examples:
    python -m evaluation.run_eval --limit 3
    python -m evaluation.run_eval --limit 10 --tag baseline
    python -m evaluation.run_eval --concurrency 2 --tag full-baseline

The script calls the same LangGraph pipeline and external services as the API.
Every case creates a trace in the observability database, then the aggregate
report is written as JSON and Markdown.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(REPO_ROOT / ".env")

from app.agents.orchestrator import plan_trip
from app.schemas.trip import TripRequest
from app.services import observability

DEFAULT_CASES = Path(__file__).resolve().parent / "cases.json"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the travel planner evaluation set.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="Path to cases JSON.")
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N cases.")
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only the given case id. Can be repeated.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of cases to run concurrently. Default is 1 to protect API quotas.",
    )
    parser.add_argument("--tag", default="", help="Report tag, e.g. baseline or after-optimization.")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument(
        "--docs-report",
        default="",
        help="Optional Markdown report path, e.g. docs/EVAL_REPORT.md.",
    )
    parser.add_argument(
        "--include-trace",
        action="store_true",
        help="Include full trace payloads in the JSON report.",
    )
    parser.add_argument(
        "--fail-under-success",
        type=float,
        default=None,
        help="Exit with status 1 when success rate is below this value.",
    )
    parser.add_argument("--dry-run", action="store_true", help="List selected cases and exit.")
    return parser.parse_args()


def load_cases(path: Path, limit: int | None, case_ids: list[str] | None) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("cases file must contain a JSON list")
    selected = [item for item in data if isinstance(item, dict)]
    if case_ids:
        wanted = set(case_ids)
        selected = [item for item in selected if str(item.get("id")) in wanted]
    if limit is not None:
        selected = selected[: max(0, limit)]
    for item in selected:
        for key in ("id", "destination", "days", "budget"):
            if key not in item:
                raise ValueError(f"case is missing required key: {key}")
    return selected


def build_request(case: dict[str, Any]) -> TripRequest:
    offset = int(case.get("travel_offset_days", 3) or 3)
    travel_date = (date.today() + timedelta(days=offset)).isoformat()
    return TripRequest(
        destination=str(case["destination"]),
        days=int(case["days"]),
        budget=int(case["budget"]),
        departure_city=str(case.get("departure_city", "")),
        travel_date=travel_date,
        pace=str(case.get("pace", "standard")),
        hotel_budget=int(case.get("hotel_budget", 0) or 0),
        dietary_notes=str(case.get("dietary_notes", "")),
        companions=int(case.get("companions", 1) or 1),
        transport_mode=str(case.get("transport_mode", "auto")),
        preferences=list(case.get("preferences") or []),
    )


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = str(case.get("id"))
    started = time.perf_counter()
    trace = None
    try:
        request = build_request(case)
        with observability.trace_generation(source="evaluation", request=request) as trace:
            plan = plan_trip(request, source="evaluation")
            trace.attach_plan(plan)
        record = trace.snapshot()
        result = _result_from_trace(case, record)
        result["plan_summary"] = record.get("plan_summary") or {}
        return result
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record = trace.snapshot() if trace is not None else {}
        return {
            "case_id": case_id,
            "destination": str(case.get("destination", "")),
            "days": int(case.get("days", 0) or 0),
            "budget": int(case.get("budget", 0) or 0),
            "success": False,
            "duration_ms": record.get("duration_ms") or duration_ms,
            "trace_id": record.get("trace_id", ""),
            "quality_passed": record.get("quality_passed"),
            "route_closed": record.get("route_closed"),
            "budget_compliant": record.get("budget_compliant"),
            "llm_tokens": record.get("llm_tokens", 0),
            "estimated_cost": record.get("estimated_cost", 0),
            "invalid_poi_count": record.get("invalid_poi_count", 0),
            "retry_count": record.get("retry_count", 0),
            "cache_hit_rate": record.get("cache_hit_rate", 0),
            "error": str(exc),
            "trace": record,
        }


def _result_from_trace(case: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": str(case.get("id")),
        "destination": str(case.get("destination", "")),
        "days": int(case.get("days", 0) or 0),
        "budget": int(case.get("budget", 0) or 0),
        "success": bool(record.get("success")),
        "duration_ms": record.get("duration_ms", 0),
        "trace_id": record.get("trace_id", ""),
        "quality_passed": record.get("quality_passed"),
        "route_closed": record.get("route_closed"),
        "budget_compliant": record.get("budget_compliant"),
        "llm_tokens": record.get("llm_tokens", 0),
        "estimated_cost": record.get("estimated_cost", 0),
        "invalid_poi_count": record.get("invalid_poi_count", 0),
        "retry_count": record.get("retry_count", 0),
        "cache_hit_rate": record.get("cache_hit_rate", 0),
        "error": record.get("error", ""),
        "trace": record,
    }


def run_all(cases: list[dict[str, Any]], concurrency: int) -> list[dict[str, Any]]:
    workers = max(1, min(concurrency, len(cases) or 1))
    if workers == 1:
        results: list[dict[str, Any]] = []
        for index, case in enumerate(cases, start=1):
            print(f"[{index}/{len(cases)}] {case.get('id')} ...", flush=True)
            result = run_case(case)
            print(
                f"    success={result['success']} duration={result['duration_ms']}ms "
                f"error={result['error'][:120]}",
                flush=True,
            )
            results.append(result)
        return results

    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_case, case): case for case in cases}
        for future in as_completed(futures):
            result = future.result()
            print(
                f"    {result['case_id']} success={result['success']} "
                f"duration={result['duration_ms']}ms",
                flush=True,
            )
            results.append(result)
    order = {str(case.get("id")): index for index, case in enumerate(cases)}
    return sorted(results, key=lambda item: order.get(item["case_id"], 9999))


def build_report(
    tag: str, cases: list[dict[str, Any]], results: list[dict[str, Any]]
) -> dict[str, Any]:
    traces = [result.get("trace") or {} for result in results]
    aggregate = observability.aggregate_records(traces, window_days=0)
    return {
        "tag": tag,
        "generated_at": aggregate.get("generated_at"),
        "cases_total": len(cases),
        "cases_run": len(results),
        "summary": aggregate,
        "results": results,
    }


def _public_results(results: list[dict[str, Any]], include_trace: bool) -> list[dict[str, Any]]:
    if include_trace:
        return results
    public: list[dict[str, Any]] = []
    for result in results:
        item = dict(result)
        item.pop("trace", None)
        public.append(item)
    return public


def _pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.1f}%"


def _num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.{digits}f}"


def _yes_no(value: Any) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    totals = summary["totals"]
    rates = summary["rates"]
    latency = summary["latency_ms"]
    tokens = summary["tokens"]
    cost = summary["cost"]
    external = summary["external"]
    cost_display = (
        f"{_num(cost.get('avg_per_run'), 6)} {cost.get('currency', 'CNY')}"
        if cost.get("configured")
        else "not configured"
    )
    lines = [
        "# AI Travel Planner Evaluation Report",
        "",
        f"- Tag: {report.get('tag') or 'baseline'}",
        f"- Generated at: {report.get('generated_at') or ''}",
        f"- Cases: {report.get('cases_run')}/{report.get('cases_total')}",
        "- Data source: real LangGraph pipeline plus configured LLM/Amap services",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Success rate | {_pct(rates.get('success_rate'))} |",
        f"| Quality pass rate | {_pct(rates.get('quality_pass_rate'))} |",
        f"| Route closure rate | {_pct(rates.get('route_closure_rate'))} |",
        f"| Budget compliance rate | {_pct(rates.get('budget_compliance_rate'))} |",
        f"| Invalid POI run rate | {_pct(rates.get('invalid_poi_run_rate'))} |",
        f"| Cache hit rate | {_pct(rates.get('cache_hit_rate'))} |",
        f"| Latency P50 | {_num(latency.get('p50'))} ms |",
        f"| Latency P95 | {_num(latency.get('p95'))} ms |",
        f"| Average tokens per run | {_num(tokens.get('avg_per_run'))} |",
        f"| Estimated cost per run | {cost_display} |",
        f"| Amap calls per run | {_num(external.get('amap_calls_avg'))} |",
        f"| Total retries | {summary.get('retries', {}).get('total', 0)} |",
        "",
        "## Per-case Results",
        "",
        "| Case | Destination | Success | Duration (ms) | Quality | Route | Budget | Tokens | Error |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in report.get("results") or []:
        error = str(result.get("error") or "").replace("|", " ")[:80]
        lines.append(
            "| {case} | {destination} | {success} | {duration} | {quality} | {route} | "
            "{budget} | {tokens} | {error} |".format(
                case=result.get("case_id", ""),
                destination=result.get("destination", ""),
                success="yes" if result.get("success") else "no",
                duration=_num(result.get("duration_ms"), 0),
                quality=_yes_no(result.get("quality_passed")),
                route=_yes_no(result.get("route_closed")),
                budget=_yes_no(result.get("budget_compliant")),
                tokens=result.get("llm_tokens", 0),
                error=error,
            )
        )

    lines.extend(
        [
            "",
            "## Node Latency",
            "",
            "| Node | Count | Avg (ms) | P95 (ms) | Max (ms) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, stats in (summary.get("nodes") or {}).items():
        lines.append(
            f"| {name} | {stats.get('count', 0)} | {_num(stats.get('avg_ms'))} | "
            f"{_num(stats.get('p95_ms'))} | {_num(stats.get('max_ms'))} |"
        )

    lines.extend(["", "## Top Errors", ""])
    top_errors = summary.get("top_errors") or []
    if top_errors:
        lines.extend(["| Error | Count |", "|---|---:|"])
        for item in top_errors:
            message = str(item.get("message") or "").replace("|", " ")[:160]
            lines.append(f"| {message} | {item.get('count', 0)} |")
    else:
        lines.append("No generation errors recorded.")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- A full run can be started with: `python -m evaluation.run_eval --concurrency 1`.",
            "- LLM cost is zero unless DEEPSEEK_INPUT_COST_PER_1M and "
            "DEEPSEEK_OUTPUT_COST_PER_1M are configured.",
            "- Traces are stored in TRACE_DB_PATH; query one run with "
            "`GET /api/metrics/traces/{trace_id}`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(
    report: dict[str, Any],
    output_dir: Path,
    tag: str,
    include_trace: bool,
    docs_report: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_tag = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in tag) or "baseline"
    json_path = output_dir / f"{safe_tag}.json"
    markdown_path = output_dir / f"{safe_tag}.md"
    payload = dict(report)
    payload["results"] = _public_results(report.get("results") or [], include_trace)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = render_markdown(payload)
    markdown_path.write_text(markdown, encoding="utf-8")
    if docs_report:
        docs_path = Path(docs_report)
        if not docs_path.is_absolute():
            docs_path = REPO_ROOT / docs_path
        docs_path.parent.mkdir(parents=True, exist_ok=True)
        docs_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    args = parse_args()
    cases = load_cases(Path(args.cases), args.limit, args.case_ids)
    if not cases:
        print("No cases selected.")
        return 1
    if args.dry_run:
        for case in cases:
            print(f"{case.get('id')} -> {case.get('destination')} {case.get('days')}d")
        return 0

    tag = args.tag or f"baseline-{date.today().isoformat()}"
    print(f"Running {len(cases)} evaluation case(s), concurrency={max(1, args.concurrency)}")
    results = run_all(cases, args.concurrency)
    report = build_report(tag, cases, results)
    json_path, markdown_path = write_reports(
        report,
        Path(args.output_dir),
        tag,
        args.include_trace,
        args.docs_report,
    )
    summary = report["summary"]
    print("")
    print(f"Report: {json_path}")
    print(f"Report: {markdown_path}")
    print(
        "Success rate: {success} | Quality: {quality} | Route: {route} | P95: {p95} ms".format(
            success=_pct(summary["rates"].get("success_rate")),
            quality=_pct(summary["rates"].get("quality_pass_rate")),
            route=_pct(summary["rates"].get("route_closure_rate")),
            p95=_num(summary["latency_ms"].get("p95")),
        )
    )
    success_rate = summary["rates"].get("success_rate")
    if args.fail_under_success is not None and (
        success_rate is None or success_rate < args.fail_under_success
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
