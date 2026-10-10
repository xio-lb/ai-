import fakeredis

from app.services import shared_cache


def _use_fake_redis():
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    shared_cache.use_client_for_tests(client)
    return server


def test_json_round_trip_and_prefix_delete():
    _use_fake_redis()
    shared_cache.set_json("demo:one", {"city": "成都", "days": 3}, 60)
    assert shared_cache.get_json("demo:one") == {"city": "成都", "days": 3}

    removed = shared_cache.delete_prefix("demo:")
    assert removed == 1
    assert shared_cache.get_json("demo:one") is None


def test_ttl_is_applied_to_shared_values():
    _use_fake_redis()
    shared_cache.set_json("demo:ttl", "value", 1)
    assert shared_cache.get_json("demo:ttl") == "value"
    shared_cache.delete_prefix("demo:")
    assert shared_cache.get_json("demo:ttl") is None


def test_hit_uses_shared_atomic_counter():
    _use_fake_redis()
    assert shared_cache.hit("rate:test", 2, 60) == (False, 1)
    assert shared_cache.hit("rate:test", 2, 60) == (False, 2)
    assert shared_cache.hit("rate:test", 2, 60) == (True, 3)

    shared_cache.reset_counter("rate:test")
    assert shared_cache.hit("rate:test", 2, 60) == (False, 1)


def test_value_written_by_one_worker_is_visible_to_another():
    server = _use_fake_redis()
    shared_cache.set_json("cross:worker", {"ok": True}, 60)

    # Simulate a second uvicorn worker: a different client, same Redis server.
    shared_cache.use_client_for_tests(
        fakeredis.FakeRedis(server=server, decode_responses=True)
    )
    assert shared_cache.get_json("cross:worker") == {"ok": True}


def test_missing_redis_falls_back_to_process_memory(monkeypatch):
    shared_cache.reset_for_tests()
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(shared_cache, "redis_module", None)

    shared_cache.set_json("fallback:key", "kept", 60)
    assert shared_cache.get_json("fallback:key") == "kept"
    assert shared_cache.health()["backend"] == "memory"
    assert shared_cache.hit("fallback:rate", 1, 60) == (False, 1)
    assert shared_cache.hit("fallback:rate", 1, 60) == (True, 2)


def test_rate_limit_is_shared_across_workers():
    server = _use_fake_redis()
    assert shared_cache.hit("rate:cross-worker", 1, 60) == (False, 1)

    shared_cache.use_client_for_tests(
        fakeredis.FakeRedis(server=server, decode_responses=True)
    )
    assert shared_cache.hit("rate:cross-worker", 1, 60) == (True, 2)


def test_current_counter_does_not_consume_quota():
    _use_fake_redis()
    assert shared_cache.current_counter("rate:peek") == 0
    shared_cache.hit("rate:peek", 5, 60)
    assert shared_cache.current_counter("rate:peek") == 1
    assert shared_cache.current_counter("rate:peek") == 1
