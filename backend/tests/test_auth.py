import time

from fastapi.testclient import TestClient

from app.main import app
from app.services import auth_service, chat_service, memory_service
from tests.conftest import _auth_headers, _register


def test_register_login_and_me():
    with TestClient(app) as client:
        account = _register(client, "alice@example.com")
        assert account["user"]["email"] == account["email"]
        assert account["token"]

        me = client.get("/api/auth/me", headers=_auth_headers(account))
        assert me.status_code == 200
        assert me.json()["user"]["id"] == account["user"]["id"]

        login = client.post(
            "/api/auth/login",
            json={"email": account["email"], "password": "test-password-123"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["id"] == account["user"]["id"]

        wrong = client.post(
            "/api/auth/login",
            json={"email": account["email"], "password": "wrong-password"},
        )
        assert wrong.status_code == 401


def test_password_hash_is_salted_and_verifiable():
    first = auth_service.hash_password("test-password-123")
    second = auth_service.hash_password("test-password-123")
    assert first != second
    assert first.startswith("pbkdf2_sha256$")
    assert auth_service.verify_password("test-password-123", first)
    assert not auth_service.verify_password("wrong-password", first)


def test_token_tampering_is_rejected():
    with TestClient(app) as client:
        account = _register(client, "tamper@example.com")
        token = account["token"]
        tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})
        assert response.status_code == 401


def test_logout_revokes_token():
    with TestClient(app) as client:
        account = _register(client, "logout@example.com")
        headers = _auth_headers(account)
        assert client.get("/api/auth/me", headers=headers).status_code == 200
        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_duplicate_email_is_rejected():
    with TestClient(app) as client:
        first = _register(client, "duplicate@example.com")
        response = client.post(
            "/api/auth/register",
            json={"email": first["email"], "password": "another-password-1"},
        )
        assert response.status_code == 400


def test_memory_is_isolated_between_users():
    with TestClient(app) as client:
        alice = _register(client, "memory-alice@example.com")
        bob = _register(client, "memory-bob@example.com")

        saved = client.put(
            "/api/memory",
            headers=_auth_headers(alice),
            json={"preferences": ["美食"], "visited_cities": ["成都"]},
        )
        assert saved.status_code == 200
        assert saved.json()["visited_cities"] == ["成都"]

        alice_memory = client.get("/api/memory", headers=_auth_headers(alice)).json()
        bob_memory = client.get("/api/memory", headers=_auth_headers(bob)).json()
        assert alice_memory["visited_cities"] == ["成都"]
        assert bob_memory["visited_cities"] == []


def test_chat_sessions_cannot_be_read_across_users():
    with TestClient(app) as client:
        alice = _register(client, "chat-alice@example.com")
        bob = _register(client, "chat-bob@example.com")

        session_id = chat_service.create_session("Alice 的对话", alice["user"]["id"])
        chat_service.append_message(session_id, "user", "成都", alice["user"]["id"])

        assert client.get(f"/api/chat/sessions/{session_id}", headers=_auth_headers(alice)).status_code == 200
        assert client.get(f"/api/chat/sessions/{session_id}", headers=_auth_headers(bob)).status_code == 404
        assert client.delete(f"/api/chat/sessions/{session_id}", headers=_auth_headers(bob)).status_code == 404
        assert chat_service.get_session(session_id, alice["user"]["id"]) is not None


def test_login_failures_are_rate_limited(monkeypatch):
    monkeypatch.setenv("AUTH_LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("AUTH_LOGIN_WINDOW_SECONDS", "900")
    subject = "bruteforce@example.com"
    for _ in range(3):
        auth_service.record_login_attempt(subject, succeeded=False)

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": subject, "password": "whatever-password"},
        )
        assert response.status_code == 429


def test_expired_token_is_rejected(monkeypatch):
    with TestClient(app) as client:
        account = _register(client, "expired@example.com")
        token, _ = auth_service.create_access_token(account["user"]["id"], ttl_seconds=-1)
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


