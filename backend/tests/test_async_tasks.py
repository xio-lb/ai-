import time

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.trip import TripPlan, TripRequest
from app.services import tasks_service
from tests.conftest import _auth_headers, _register


def _fake_plan(req: TripRequest, **kwargs) -> TripPlan:
    plan = TripPlan(
        destination=req.destination,
        days=req.days,
        budget=req.budget,
        preferences=list(req.preferences or []),
        overview="异步任务测试行程",
        daily_plans=[],
        total_cost=min(req.budget, 1000),
        notes=[],
        budget_report=None,
    )
    object.__setattr__(plan, "_trace_id", "test-trace-id")
    return plan


def _wait_status(client: TestClient, task_id: str, headers: dict, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/tasks/{task_id}", headers=headers)
        assert response.status_code == 200
        task = response.json()
        if task["status"] in tasks_service.TERMINAL_STATUSES:
            return task
        time.sleep(0.1)
    raise AssertionError("任务未在超时时间内结束")


def test_async_task_completes_and_exposes_plan(monkeypatch):
    monkeypatch.setattr(tasks_service, "plan_trip", _fake_plan)
    with TestClient(app) as client:
        account = _register(client, "task-owner@example.com")
        headers = _auth_headers(account)

        submitted = client.post(
            "/api/tasks/plan",
            headers=headers,
            json={"request": {"destination": "成都", "days": 2, "budget": 2000}},
        )
        assert submitted.status_code == 202
        task_id = submitted.json()["task_id"]

        task = _wait_status(client, task_id, headers)
        assert task["status"] == "succeeded"
        assert task["plan"]["destination"] == "成都"
        assert task["trace_id"] == "test-trace-id"

        listing = client.get("/api/tasks", headers=headers).json()["items"]
        assert any(item["task_id"] == task_id for item in listing)


def test_async_task_is_isolated_between_users():
    with TestClient(app) as client:
        alice = _register(client, "task-alice@example.com")
        bob = _register(client, "task-bob@example.com")
        task = tasks_service.create_task(
            alice["user"]["id"],
            TripRequest(destination="成都", days=1, budget=1000),
        )
        assert client.get(f"/api/tasks/{task['task_id']}", headers=_auth_headers(alice)).status_code == 200
        assert client.get(f"/api/tasks/{task['task_id']}", headers=_auth_headers(bob)).status_code == 404
        assert client.post(f"/api/tasks/{task['task_id']}/cancel", headers=_auth_headers(bob)).status_code == 404


def test_async_task_can_be_cancelled(monkeypatch):
    monkeypatch.setattr(tasks_service, "plan_trip", _fake_plan)
    with TestClient(app) as client:
        account = _register(client, "task-cancel@example.com")
        headers = _auth_headers(account)
        task = tasks_service.create_task(
            account["user"]["id"],
            TripRequest(destination="重庆", days=1, budget=1000),
        )
        cancelled = client.post(f"/api/tasks/{task['task_id']}/cancel", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["ok"] is True

        deadline = time.time() + 5
        status = None
        while time.time() < deadline:
            status = client.get(f"/api/tasks/{task['task_id']}", headers=headers).json()
            if status["status"] in tasks_service.TERMINAL_STATUSES:
                break
            time.sleep(0.1)
        assert status is not None
        assert status["status"] in {"cancelled", "succeeded"}


def test_submit_rate_limit(monkeypatch):
    monkeypatch.setattr(tasks_service, "SUBMIT_MAX_PER_WINDOW", 1)
    with TestClient(app) as client:
        account = _register(client, "task-rate@example.com")
        headers = _auth_headers(account)
        payload = {"request": {"destination": "成都", "days": 1, "budget": 1000}}
        first = client.post("/api/tasks/plan", headers=headers, json=payload)
        assert first.status_code == 202
        second = client.post("/api/tasks/plan", headers=headers, json=payload)
        assert second.status_code == 429
