from fastapi.testclient import TestClient

from app.main import _friendly_error, app
from app.services import amap_client, cache_service

client = TestClient(app)


def test_unknown_route_returns_chinese_message():
    response = client.get("/api/not-exist")
    assert response.status_code == 404
    assert "请求的接口不存在" in response.json()["detail"]


def test_validation_error_returns_chinese_message():
    response = client.post("/api/trip/plan", json={})
    assert response.status_code == 422
    assert "请求参数有误" in response.json()["detail"]


def test_friendly_error_keeps_chinese_and_hides_english():
    assert "高德地图" in _friendly_error(RuntimeError("高德地图搜索失败：test"))
    assert "服务暂时不可用" in _friendly_error(RuntimeError("boom"))
    assert "AI 服务暂时不可用" in _friendly_error(RuntimeError("OpenAI API error"))


def test_amap_search_error_is_chinese(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_service, "DB_PATH", tmp_path / "cache.db")
    cache_service.init_db()

    class FakeResponse:
        def json(self):
            return {"status": "0", "info": "USER_DAILY_QUERY_OVER_LIMIT"}

    monkeypatch.setattr(amap_client.httpx, "get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(amap_client, "_poi_cache", {})
    try:
        amap_client._search_pois("TestCity", "TestKeyword", limit=1)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "高德地图" in str(exc)
