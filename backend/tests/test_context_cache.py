from app.services import context_cache


def test_context_cache_hits_same_scope_and_isolates_keywords():
    context_cache.reset_for_tests()
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        return ["宽窄巷子"]

    first, first_hit = context_cache.get_or_load(
        "attractions", "成都", loader, scope="2026-10", keywords=["人文", "博物馆"]
    )
    second, second_hit = context_cache.get_or_load(
        "attractions", "成都", loader, scope="2026-10", keywords=["博物馆", "人文"]
    )
    other, other_hit = context_cache.get_or_load(
        "attractions", "成都", loader, scope="2026-10", keywords=["美食"]
    )

    assert first_hit is False
    assert second_hit is True
    assert other_hit is False
    assert first == second == other == ["宽窄巷子"]
    assert calls["count"] == 2


def test_context_cache_isolates_destination_and_scope():
    context_cache.reset_for_tests()
    calls = {"count": 0}

    def loader():
        calls["count"] += 1
        return calls["count"]

    context_cache.get_or_load("weather", "成都", loader, scope="2026-10", keywords=["2026-10-10"])
    context_cache.get_or_load("weather", "重庆", loader, scope="2026-10", keywords=["2026-10-10"])
    context_cache.get_or_load("weather", "成都", loader, scope="2026-11", keywords=["2026-11-10"])

    assert calls["count"] == 3
    assert context_cache.stats()["misses"] == 3