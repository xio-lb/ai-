from app.schemas.trip import DayPlan, Spot, TripPlan, TripRequest
from app.services import cache_service, observability


def _use_temp_trace_db(monkeypatch, tmp_path):
    monkeypatch.setattr(observability, "DB_PATH", tmp_path / "trace.db")
    observability.reset_for_tests()
    observability.init_db()


def test_trace_records_generation_metrics(monkeypatch, tmp_path):
    _use_temp_trace_db(monkeypatch, tmp_path)
    request = TripRequest(
        destination="成都",
        days=2,
        budget=2000,
        departure_city="北京",
        pace="standard",
    )

    with observability.trace_generation(source="test", request=request) as trace:
        observability.record_node("analyze", 12.5)
        observability.record_llm_call(
            "requirement_analyze",
            "deepseek-chat",
            "prompthash",
            "v1",
            20.0,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost=0.01,
        )
        observability.record_external_call("amap", "poi_search", 15.0, True)
        observability.record_cache_event("amap", True)
        observability.record_quality(
            {"passed": False, "issues": ["景点不在候选清单：不存在景点"]}
        )
        observability.record_budget(
            {
                "budget": 2000,
                "total_cost": 1500,
                "within_budget": True,
                "savings": 500,
            }
        )
        observability.record_route(["第1天路线没有返回酒店"])
        plan = TripPlan(
            destination="成都",
            days=2,
            budget=2000,
            total_cost=1500,
            daily_plans=[
                DayPlan(
                    day=1,
                    theme="人文",
                    spots=[Spot(name="不存在景点", location="104.06,30.67")],
                    foods=[],
                )
            ],
            quality_report={
                "passed": False,
                "issues": ["景点不在候选清单：不存在景点"],
            },
            budget_report={
                "budget": 2000,
                "total_cost": 1500,
                "within_budget": True,
                "savings": 500,
            },
        )
        trace.attach_plan(plan)

    record = observability.get_trace(trace.trace_id)
    assert record is not None
    assert record["status"] == "success"
    assert record["success"] is True
    assert record["llm_tokens"] == 150
    assert record["amap_calls"] == 1
    assert record["cache_hit_rate"] == 1.0
    assert record["invalid_poi_count"] == 1
    assert record["route_closed"] is False
    assert record["budget_compliant"] is True
    assert record["plan_summary"]["spots"] == 1

    summary = observability.summary(days=1)
    assert summary["totals"]["runs"] == 1
    assert summary["rates"]["success_rate"] == 1.0
    assert summary["rates"]["route_closure_rate"] == 0.0
    assert summary["nodes"]["analyze"]["avg_ms"] == 12.5


def test_trace_records_failure(monkeypatch, tmp_path):
    _use_temp_trace_db(monkeypatch, tmp_path)

    try:
        with observability.trace_generation(source="test") as trace:
            observability.record_node("itinerary", 5.0, "error", "boom")
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    record = observability.get_trace(trace.trace_id)
    assert record is not None
    assert record["status"] == "failure"
    assert record["success"] is False
    assert "boom" in record["error"]


def test_percentile_and_prometheus_output():
    assert observability.percentile([10, 20, 30, 40], 0.5) == 25.0
    assert observability.percentile([10, 20, 30, 40], 0.95) == 38.5
    text = observability.prometheus_text(days=1)
    assert "travel_planner_runs_total" in text
    assert "travel_planner_generation_duration_ms" in text


def test_cache_hits_are_recorded_in_trace(monkeypatch, tmp_path):
    _use_temp_trace_db(monkeypatch, tmp_path)
    monkeypatch.setattr(cache_service, "DB_PATH", tmp_path / "cache.db")
    cache_service.init_db()

    with observability.trace_generation(source="test") as trace:
        cache_service.set_cached("test", "hit", "value", ttl_seconds=3600)
        assert cache_service.get_cached("test", "hit") == "value"
        assert cache_service.get_cached("test", "miss") is None

    record = trace.snapshot()
    assert record["cache_hits"] == 1
    assert record["cache_lookups"] == 2
