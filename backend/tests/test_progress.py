from types import SimpleNamespace

from app.services import amap_client, cache_service, progress


def test_report_progress_calls_callback():
    messages: list[str] = []
    token = progress.set_progress_callback(messages.append)
    try:
        progress.report_progress("正在搜索：测试")
    finally:
        progress.reset_progress_callback(token)
    assert messages == ["正在搜索：测试"]


def test_report_progress_without_callback_is_noop():
    progress.report_progress("test")


def test_search_pois_reports_search_message(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_service, "DB_PATH", tmp_path / "cache.db")
    cache_service.init_db()
    messages: list[str] = []
    token = progress.set_progress_callback(messages.append)
    try:
        def fake_get(url, params=None, timeout=None):
            return SimpleNamespace(json=lambda: {"status": "1", "pois": []})

        monkeypatch.setattr(amap_client.httpx, "get", fake_get)
        monkeypatch.setattr(amap_client, "_poi_cache", {})
        amap_client._search_pois("TestCity", "TestKeyword", limit=1)
    finally:
        progress.reset_progress_callback(token)
    assert any("正在搜索" in message for message in messages)
