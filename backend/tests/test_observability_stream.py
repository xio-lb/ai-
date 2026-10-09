import queue

from app import main
from app.schemas.trip import TripPlan, TripRequest
from app.services import observability


def test_stream_run_finalizes_trace(monkeypatch, tmp_path):
    monkeypatch.setattr(observability, "DB_PATH", tmp_path / "trace.db")
    observability.reset_for_tests()
    observability.init_db()

    plan = TripPlan(destination="成都", days=1, budget=1000, total_cost=800)

    def fake_stream(state, stream_mode):
        yield {"analyze": {}}
        yield {"surrounding": {"plan": plan}}

    monkeypatch.setattr(main.trip_graph, "stream", fake_stream)
    events: queue.Queue = queue.Queue()
    main._run_plan_stream(
        TripRequest(destination="成都", days=1, budget=1000),
        events,
    )

    received = []
    while True:
        item = events.get(timeout=1)
        received.append(item)
        if item.get("type") == "exit":
            break

    assert any(item.get("type") == "done" for item in received)
    summary = observability.summary(days=1)
    assert summary["totals"]["runs"] == 1
    assert summary["rates"]["success_rate"] == 1.0
