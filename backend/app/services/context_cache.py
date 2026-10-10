"""Retrieval cache for agent-level candidate pools.

Two layers of caching already exist for external calls (an in-memory dict inside
``amap_client`` and a SQLite table behind it). This layer is different: it caches
the *agent-level* candidate sets, so generating three theme variants reuses one
``attractions`` / ``foods`` / ``hotels`` / ``weather`` result instead of running
the whole Agent pipeline three times.

Entries are keyed by destination, travel month and the requirement keyword set.
Different themes ask Amap for different candidate pools, so keying only by city
would feed one variant another variant's results. Requests that repeat the same
destination, month and preference keywords still hit the same pool, while the
lower-level Amap cache keeps sharing individual POI queries across variants.

The cache has two layers: an in-process LRU (fast, bounded) and an optional
Redis layer. Redis is what makes the pool shared across uvicorn workers or
containers; a local hit still avoids the network round trip, while a Redis hit
backfills the local layer. When Redis is not configured the module behaves
exactly like the original process-local cache.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from app.schemas.trip import (
    AttractionCandidate,
    FoodCandidate,
    HotelCandidate,
    WeatherInfo,
)
from app.services import shared_cache

MAX_ENTRIES = 128
DEFAULT_TTL_SECONDS = 30 * 60

_lock = threading.Lock()
_store: "OrderedDict[tuple, tuple[float, Any]]" = OrderedDict()
_stats = {"hits": 0, "misses": 0, "stores": 0}

_LIST_MODELS: dict[str, Any] = {
    "attractions": AttractionCandidate,
    "foods": FoodCandidate,
    "hotels": HotelCandidate,
}
_SINGLE_MODELS: dict[str, Any] = {
    "weather": WeatherInfo,
}


def _key(kind: str, destination: str, scope: str = "") -> tuple:
    return (kind, destination.strip(), scope.strip())


def _shared_key(kind: str, destination: str, scope: str = "") -> str:
    return f"context:{kind}:{destination.strip()}:{scope.strip()}"


def _encode(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [item.model_dump() if hasattr(item, "model_dump") else item for item in value]
    return value


def _decode(kind: str, value: Any) -> Any:
    if value is None:
        return value
    if kind in _SINGLE_MODELS:
        return _SINGLE_MODELS[kind].model_validate(value)
    model = _LIST_MODELS.get(kind)
    if model is None:
        return value
    return [model.model_validate(item) for item in value]


def _purge_expired(now: float) -> None:
    expired = [key for key, (expires_at, _) in _store.items() if expires_at <= now]
    for key in expired:
        _store.pop(key, None)


def get_or_load(
    kind: str,
    destination: str,
    loader: Callable[[], Any],
    scope: str = "",
    keywords: list[str] | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> tuple[Any, bool]:
    """Return ``(value, cache_hit)``; call ``loader`` only on a miss."""
    keyword_scope = ",".join(
        sorted({str(keyword).strip() for keyword in (keywords or []) if str(keyword).strip()})
    )
    if keyword_scope:
        scope = f"{scope}|{keyword_scope}" if scope else keyword_scope
    key = _key(kind, destination, scope)
    redis_key = _shared_key(kind, destination, scope)
    now = time.time()

    with _lock:
        _purge_expired(now)
        entry = _store.get(key)
        if entry is not None and entry[0] > now:
            _store.move_to_end(key)
            _stats["hits"] += 1
            return entry[1], True

    shared_value = shared_cache.get_json(redis_key)
    if shared_value is not None:
        value = _decode(kind, shared_value)
        with _lock:
            _store[key] = (now + ttl_seconds, value)
            _store.move_to_end(key)
            while len(_store) > MAX_ENTRIES:
                _store.popitem(last=False)
            _stats["hits"] += 1
            _stats["stores"] += 1
        return value, True

    value = loader()
    encoded = _encode(value)

    with _lock:
        _store[key] = (now + ttl_seconds, value)
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)
        _stats["misses"] += 1
        _stats["stores"] += 1
    shared_cache.set_json(redis_key, encoded, max(1, int(ttl_seconds)))
    return value, False


def put(kind: str, destination: str, value: Any, scope: str = "", ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
    key = _key(kind, destination, scope)
    with _lock:
        _store[key] = (time.time() + ttl_seconds, value)
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)
        _stats["stores"] += 1
    shared_cache.set_json(_shared_key(kind, destination, scope), _encode(value), max(1, int(ttl_seconds)))


def invalidate(destination: str = "") -> int:
    destination = destination.strip()
    if destination:
        shared_cache.delete_prefix(f"context:*:{destination}:")
    else:
        shared_cache.delete_prefix("context:")
    with _lock:
        if not destination:
            count = len(_store)
            _store.clear()
            return count
        keys = [key for key in _store if key[1] == destination]
        for key in keys:
            _store.pop(key, None)
        return len(keys)


def stats() -> dict:
    with _lock:
        shared = shared_cache.stats()
        return {
            "entries": len(_store),
            "hits": _stats["hits"],
            "misses": _stats["misses"],
            "stores": _stats["stores"],
            "shared_hits": shared["hits"],
            "shared_misses": shared["misses"],
            "shared_backend": shared_cache.health()["backend"],
            "hit_rate": round(
                _stats["hits"] / max(1, _stats["hits"] + _stats["misses"]),
                4,
            ),
        }


def reset_for_tests() -> None:
    with _lock:
        _store.clear()
        _stats.update({"hits": 0, "misses": 0, "stores": 0})
