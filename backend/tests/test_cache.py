from types import SimpleNamespace

import fakeredis

from app.schemas.trip import RouteInfo
from app.services import amap_client, cache_service, shared_cache


def _temp_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(cache_service, "DB_PATH", tmp_path / "amap_test.db")
    cache_service.init_db()


def test_cache_round_trip_and_expiry(monkeypatch, tmp_path):
    _temp_cache(monkeypatch, tmp_path)
    cache_service.set_cached(
        "test", "roundtrip", {"a": 1, "b": [2, 3]}, ttl_seconds=3600
    )
    assert cache_service.get_cached("test", "roundtrip") == {"a": 1, "b": [2, 3]}
    cache_service.set_cached("test", "expired", "value", ttl_seconds=0)
    assert cache_service.get_cached("test", "expired") is None


def test_shared_cache_hit_skips_sqlite(monkeypatch, tmp_path):
    _temp_cache(monkeypatch, tmp_path)
    cache_service.set_cached("amap", "hot-layer", {"cached": "sqlite"}, ttl_seconds=3600)
    shared_cache.use_client_for_tests(
        fakeredis.FakeRedis(decode_responses=True)
    )
    shared_cache.set_json("cache:amap:hot-layer", {"cached": "redis"}, 3600)

    def fail_connect():
        raise AssertionError("shared cache should be checked before SQLite")

    monkeypatch.setattr(cache_service, "_connect", fail_connect)
    assert cache_service.get_cached("amap", "hot-layer") == {"cached": "redis"}


def test_redis_miss_backfills_from_sqlite(monkeypatch, tmp_path):
    shared_cache.use_client_for_tests(
        fakeredis.FakeRedis(decode_responses=True)
    )
    _temp_cache(monkeypatch, tmp_path)
    cache_service.set_cached("amap", "warm-layer", {"cached": True}, ttl_seconds=3600)
    shared_cache.clear()

    assert cache_service.get_cached("amap", "warm-layer") == {"cached": True}

    def fail_connect():
        raise AssertionError("backfilled Redis value should avoid SQLite")

    monkeypatch.setattr(cache_service, "_connect", fail_connect)
    assert cache_service.get_cached("amap", "warm-layer") == {"cached": True}


def test_get_route_uses_persistent_cache(monkeypatch, tmp_path):
    _temp_cache(monkeypatch, tmp_path)
    calls = {"count": 0}

    def fake_fetch(origin, destination, mode, city=""):
        calls["count"] += 1
        return RouteInfo(
            mode=mode,
            duration_seconds=180,
            distance_meters=900,
            duration_text="3 minutes",
            distance_text="900 m",
            polyline=f"{origin};{destination}",
        )

    monkeypatch.setattr(amap_client, "_fetch_route", fake_fetch)
    monkeypatch.setattr(amap_client, "_route_cache", {})
    first = amap_client.get_route(
        "116.40,39.90", "116.41,39.91", mode="driving", city="TestCity"
    )
    assert first.duration_seconds == 180

    monkeypatch.setattr(amap_client, "_route_cache", {})
    second = amap_client.get_route(
        "116.40,39.90", "116.41,39.91", mode="driving", city="TestCity"
    )
    assert second.duration_seconds == 180
    assert calls["count"] == 1


def test_search_pois_uses_persistent_cache(monkeypatch, tmp_path):
    _temp_cache(monkeypatch, tmp_path)
    calls = {"count": 0}

    def fake_get(url, params=None, timeout=None):
        calls["count"] += 1
        return SimpleNamespace(
            json=lambda: {
                "status": "1",
                "pois": [
                    {
                        "name": "TestAttraction",
                        "location": "104.06,30.67",
                        "type": "\u98ce\u666f\u540d\u80dc",
                    }
                ],
            }
        )

    monkeypatch.setattr(amap_client.httpx, "get", fake_get)
    monkeypatch.setattr(amap_client, "_poi_cache", {})
    first = amap_client._search_pois("TestCity", "TestKeyword", types="", limit=2)
    monkeypatch.setattr(amap_client, "_poi_cache", {})
    second = amap_client._search_pois("TestCity", "TestKeyword", types="", limit=2)
    assert first == second
    assert calls["count"] == 1


def test_get_weather_uses_persistent_cache(monkeypatch, tmp_path):
    _temp_cache(monkeypatch, tmp_path)
    calls = {"count": 0}

    def fake_get(url, params=None, timeout=None):
        calls["count"] += 1
        return SimpleNamespace(
            json=lambda: {
                "status": "1",
                "lives": [
                    {
                        "city": "TestCity",
                        "weather": "Sunny",
                        "temperature": "28",
                        "winddirection": "East",
                        "windpower": "3",
                        "humidity": "50",
                        "reporttime": "2026-08-14 12:00:00",
                    }
                ],
            }
        )

    monkeypatch.setattr(amap_client.httpx, "get", fake_get)
    first = amap_client.get_weather("TestCity", "2026-08-20")
    second = amap_client.get_weather("TestCity", "2026-08-20")
    assert first.weather == "Sunny"
    assert second.weather == "Sunny"
    assert calls["count"] == 1
