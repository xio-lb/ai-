from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.services import chat_service, memory_service
from tests.conftest import _auth_headers, _register


def test_chat_session_service_crud(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_service, "DB_PATH", tmp_path / "chat.db")
    chat_service.init_db()

    session_id = chat_service.create_session("测试会话")
    assert chat_service.get_session(session_id)["title"] == "测试会话"

    chat_service.append_message(session_id, "user", "我想去成都")
    chat_service.append_message(session_id, "assistant", "好的，计划几天？")
    messages = chat_service.get_messages(session_id)
    assert [item["role"] for item in messages] == ["user", "assistant"]

    sessions = chat_service.list_sessions()
    assert sessions[0]["id"] == session_id
    assert sessions[0]["message_count"] == 2

    chat_service.rename_session(session_id, "成都 3日游")
    assert chat_service.get_session(session_id)["title"] == "成都 3日游"

    assert chat_service.delete_session(session_id) is True
    assert chat_service.get_session(session_id) is None
    assert chat_service.get_messages(session_id) == []


def test_chat_session_api(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_service, "DB_PATH", tmp_path / "chat-api.db")
    chat_service.init_db()

    with TestClient(app) as client:
        account = _register(client, "chat-owner@example.com")
        headers = _auth_headers(account)
        user_id = account["user"]["id"]

        session_id = chat_service.create_session("历史对话", user_id)
        chat_service.append_message(session_id, "user", "想去重庆", user_id)
        chat_service.append_message(session_id, "assistant", "预算大概多少？", user_id)

        sessions = client.get("/api/chat/sessions", headers=headers)
        assert sessions.status_code == 200
        assert sessions.json()[0]["message_count"] == 2

        detail = client.get(f"/api/chat/sessions/{session_id}", headers=headers)
        assert detail.status_code == 200
        assert len(detail.json()["messages"]) == 2

        deleted = client.delete(f"/api/chat/sessions/{session_id}", headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True

        missing = client.get(f"/api/chat/sessions/{session_id}", headers=headers)
        assert missing.status_code == 404


def test_chat_api_saves_session(tmp_path, monkeypatch):
    db_path = tmp_path / "chat-save.db"
    monkeypatch.setattr(chat_service, "DB_PATH", db_path)
    monkeypatch.setattr(memory_service, "DB_PATH", db_path)
    memory_service.init_db()
    chat_service.init_db()

    def fake_chat_requirement(messages, memory=None):
        return {
            "reply": "好的，为你规划成都 3 日游。",
            "ready": True,
            "trip_request": {
                "destination": "成都",
                "days": 3,
                "budget": 3000,
                "preferences": ["美食"],
            },
        }

    monkeypatch.setattr(main_module, "chat_requirement", fake_chat_requirement)

    with TestClient(app) as client:
        account = _register(client, "chat-save@example.com")
        headers = _auth_headers(account)
        response = client.post(
            "/api/chat",
            headers=headers,
            json={"messages": [{"role": "user", "content": "我想去成都玩 3 天"}]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "成都 3日游"

        detail = client.get(f"/api/chat/sessions/{data['session_id']}", headers=headers)
        assert detail.status_code == 200
        roles = [item["role"] for item in detail.json()["messages"]]
        assert roles == ["user", "assistant"]
        assert detail.json()["messages"][0]["content"] == "我想去成都玩 3 天"
