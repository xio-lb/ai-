from fastapi.testclient import TestClient

from app.main import app
from app.schemas.trip import TripPlan
from app.services import history_service, memory_service


def test_history_crud(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(history_service, "DB_PATH", db_path)
    monkeypatch.setattr(memory_service, "DB_PATH", db_path)
    history_service.init_db()

    plan = TripPlan(
        destination="成都",
        days=1,
        budget=1000,
        preferences=["美食"],
        overview="测试行程",
        daily_plans=[],
        total_cost=500,
        notes=[],
        budget_report=None,
    )
    plan_id = history_service.save_plan(plan)
    assert plan_id > 0

    items = history_service.list_plans()
    assert any(item["id"] == plan_id for item in items)

    loaded = history_service.get_plan(plan_id)
    assert loaded is not None
    assert loaded.destination == "成都"
    assert loaded.budget == 1000

    assert history_service.delete_plan(plan_id) is True
    assert history_service.get_plan(plan_id) is None


def test_history_delete_api(tmp_path, monkeypatch):
    db_path = tmp_path / "test-api.db"
    monkeypatch.setattr(history_service, "DB_PATH", db_path)
    monkeypatch.setattr(memory_service, "DB_PATH", db_path)
    history_service.init_db()

    plan = TripPlan(
        destination="成都",
        days=2,
        budget=2000,
        preferences=["美食"],
        overview="测试行程",
        daily_plans=[],
        total_cost=1200,
        notes=[],
        budget_report=None,
    )
    plan_id = history_service.save_plan(plan)

    with TestClient(app) as client:
        response = client.delete(f"/api/history/{plan_id}")
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert client.get(f"/api/history/{plan_id}").status_code == 404
        assert client.delete(f"/api/history/{plan_id}").status_code == 404
