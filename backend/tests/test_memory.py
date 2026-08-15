from app.schemas.trip import TripPlan, TripRequest
from app.services import memory_service


def _init_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_service, "DB_PATH", tmp_path / "memory.db")
    memory_service.init_db()
    return memory_service


def test_save_and_get_memory(tmp_path, monkeypatch):
    svc = _init_memory(tmp_path, monkeypatch)
    svc.save_user_memory(
        {
            "preferences": ["美食", "人文"],
            "visited_cities": ["成都", "重庆"],
            "dietary_notes": "不吃辣",
            "pace": "relaxed",
            "transport_mode": "walking",
            "hotel_budget": 300,
            "companions": 2,
        }
    )
    memory = svc.get_user_memory()
    assert memory["preferences"] == ["美食", "人文"]
    assert memory["visited_cities"] == ["成都", "重庆"]
    assert memory["dietary_notes"] == "不吃辣"
    assert memory["pace"] == "relaxed"
    assert memory["hotel_budget"] == 300
    assert memory["companions"] == 2


def test_merge_memory_into_request(tmp_path, monkeypatch):
    svc = _init_memory(tmp_path, monkeypatch)
    svc.save_user_memory(
        {
            "preferences": ["美食", "人文"],
            "visited_cities": ["成都"],
            "dietary_notes": "不吃辣",
            "pace": "relaxed",
            "transport_mode": "walking",
            "hotel_budget": 300,
            "companions": 2,
        }
    )
    req = TripRequest(destination="重庆", days=3, budget=2000, preferences=["拍照"])
    merged = svc.merge_memory_into_request(req)
    assert merged.preferences == ["拍照", "美食", "人文"]
    assert merged.dietary_notes == "不吃辣"
    assert merged.pace == "relaxed"
    assert merged.transport_mode == "walking"
    assert merged.hotel_budget == 300
    assert merged.companions == 2


def test_update_memory_from_plan(tmp_path, monkeypatch):
    svc = _init_memory(tmp_path, monkeypatch)
    plan = TripPlan(
        destination="成都",
        days=2,
        budget=1000,
        user_preferences=["美食", "人文"],
        dietary_notes="素食",
        hotel_budget=400,
        companions=3,
        variant_pace="relaxed",
        transport_mode="transit",
    )
    svc.update_memory_from_plan(plan)
    memory = svc.get_user_memory()
    assert memory["preferences"] == ["美食", "人文"]
    assert memory["visited_cities"] == ["成都"]
    assert memory["dietary_notes"] == "素食"
    assert memory["hotel_budget"] == 400
    assert memory["companions"] == 3
    assert memory["pace"] == "relaxed"
    assert memory["transport_mode"] == "transit"