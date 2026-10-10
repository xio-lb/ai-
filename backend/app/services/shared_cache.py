"""Redis-first shared cache with an in-memory fallback.

The project used to keep every cache and rate-limit counter inside a single
process. That is fine for one uvicorn worker, but two workers would each keep
their own candidate pool, their own Amap results and their own submit counter.
This module introduces one small abstraction on top of Redis:

* ``get_json`` / ``set_json`` / ``delete`` for shared values;
* ``hit`` for atomic fixed-window counters (rate limiting);
* ``health`` so /health can show which backend is active.

Redis is deliberately optional. When ``REDIS_URL`` is empty, the redis package
is missing, or the server is unreachable, every call transparently falls back to
an in-process store. The application therefore keeps working with zero
configuration, while production gains cross-worker cache hits and limits by
setting one environment variable.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any

try:  # Optional dependency: the app still runs without it.
    import redis as redis_module
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - exercised only in minimal installs
    redis_module = None  # type: ignore[assignment]

    class RedisError(Exception):  # type: ignore[no-redef]
        """Fallback error type when redis-py is not installed."""

LOGGER = logging.getLogger(__name__)

MAX_MEMORY_ENTRIES = 512
MAX_COUNTER_ENTRIES = 2048
FAILURE_COOLDOWN_SECONDS = 30

_client = None
_client_lock = threading.Lock()
_failure_until = 0.0
_logged_unavailable = False

_memory_lock = threading.Lock()
_memory_store: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_memory_counters: "OrderedDict[str, tuple[int, float]]" = OrderedDict()
_stats = {"hits": 0, "misses": 0, "stores": 0, "fallbacks": 0}

_DEFAULT_PREFIX = "atp"
_DEFAULT_PREFIX_LOCK = threading.Lock()
_active_prefix: str | None = None


def _prefix() -> str:
    """Read the key prefix lazily so deployment and tests can reconfigure it."""
    global _active_prefix
    if _active_prefix is not None:
        return _active_prefix
    configured = os.getenv("REDIS_KEY_PREFIX", _DEFAULT_PREFIX).strip()
    with _DEFAULT_PREFIX_LOCK:
        if _active_prefix is None:
            _active_prefix = configured or _DEFAULT_PREFIX
        return _active_prefix


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "").strip()


def _now() -> float:
    return time.time()


def _purge_memory() -> None:
    now = _now()
    expired = [key for key, (expires_at, _) in _memory_store.items() if expires_at <= now]
    for key in expired:
        _memory_store.pop(key, None)
    for key, (_, expires_at) in list(_memory_counters.items()):
        if expires_at <= now:
            _memory_counters.pop(key, None)


def get_client():
    """Return the configured Redis client, or None when Redis is not usable."""
    global _client, _logged_unavailable, _failure_until
    if _client is not None:
        return _client

    url = _redis_url()
    if not url or redis_module is None:
        return None

    with _client_lock:
        if _client is not None:
            return _client
        if _failure_until > _now():
            return None
        try:
            client = redis_module.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                health_check_interval=30,
            )
            client.ping()
        except Exception as exc:  # pragma: no cover - depends on environment
            _failure_until = _now() + FAILURE_COOLDOWN_SECONDS
            if not _logged_unavailable:
                LOGGER.warning("Redis 不可用，缓存自动降级为本进程内存实现: %s", exc)
                _logged_unavailable = True
            return None
        _client = client
        _logged_unavailable = False
        return _client


def _mark_failure(exc: Exception) -> None:
    global _client, _failure_until, _logged_unavailable
    _failure_until = _now() + FAILURE_COOLDOWN_SECONDS
    _client = None
    if not _logged_unavailable:
        LOGGER.warning("Redis 运行异常，暂时降级为本进程内存实现: %s", exc)
        _logged_unavailable = True


def _key(key: str) -> str:
    prefix = _prefix()
    return key if key.startswith(f"{prefix}:") else f"{prefix}:{key}"


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode(payload: Any) -> Any:
    if payload is None:
        return None
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except ValueError:
            return payload
    return payload


def get_json(key: str) -> Any:
    memory_key = key
    client = get_client()
    if client is not None:
        try:
            payload = client.get(_key(key))
        except RedisError as exc:
            _mark_failure(exc)
        except Exception as exc:
            _mark_failure(exc)
        else:
            if payload is not None:
                with _memory_lock:
                    _stats["hits"] += 1
                return _decode(payload)

    with _memory_lock:
        _purge_memory()
        entry = _memory_store.get(memory_key)
        if entry is not None and entry[0] > _now():
            _memory_store.move_to_end(memory_key)
            _stats["hits"] += 1
            return _decode(entry[1])
        _stats["misses"] += 1
    return None


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    memory_key = key
    ttl = max(0, int(ttl_seconds))
    encoded = _encode(value)
    client = get_client()
    stored_shared = False
    if client is not None:
        try:
            if ttl > 0:
                client.set(_key(key), encoded, ex=ttl)
            else:
                client.set(_key(key), encoded)
            stored_shared = True
        except Exception as exc:
            _mark_failure(exc)

    # When Redis is serving, keep only the shared copy. The process-local
    # OrderedDict is the fallback path, not a second full-size mirror.
    if stored_shared:
        return

    with _memory_lock:
        _purge_memory()
        if ttl <= 0:
            _memory_store.pop(memory_key, None)
            return
        _memory_store[memory_key] = (_now() + ttl, encoded)
        _memory_store.move_to_end(memory_key)
        while len(_memory_store) > MAX_MEMORY_ENTRIES:
            _memory_store.popitem(last=False)
        _stats["stores"] += 1


def delete(key: str) -> int:
    memory_key = key
    removed = 0
    client = get_client()
    if client is not None:
        try:
            removed = int(client.delete(_key(key)) or 0)
        except Exception as exc:
            _mark_failure(exc)
    with _memory_lock:
        if _memory_store.pop(memory_key, None) is not None:
            removed += 1
    return removed


def delete_prefix(prefix: str) -> int:
    """Delete all keys under ``prefix``; used for cache invalidation."""
    removed = 0
    client = get_client()
    if client is not None:
        try:
            pattern = _key(f"{prefix}*")
            keys = list(client.scan_iter(match=pattern, count=200))
            if keys:
                removed += int(client.delete(*keys) or 0)
        except Exception as exc:
            _mark_failure(exc)
    with _memory_lock:
        for key in [item for item in _memory_store if item.startswith(prefix)]:
            _memory_store.pop(key, None)
            removed += 1
    return removed


def clear() -> None:
    client = get_client()
    if client is not None:
        try:
            keys = list(client.scan_iter(match=_key("*"), count=200))
            if keys:
                client.delete(*keys)
        except Exception as exc:
            _mark_failure(exc)
    with _memory_lock:
        _memory_store.clear()
        _memory_counters.clear()


def hit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Fixed-window counter. Returns ``(exceeded, current_count)``.

    ``INCR`` is atomic across workers. The key gets its TTL on the first hit of
    the window, so the fixed window stays aligned to the first request. The
    tiny gap between ``INCR`` and ``EXPIRE`` only matters if the process dies
    mid-call; the in-memory fallback covers that case until the next restart.
    """
    window = max(1, int(window_seconds))
    maximum = max(1, int(limit))
    client = get_client()
    if client is not None:
        try:
            redis_key = _key(key)
            current = int(client.incr(redis_key) or 0)
            if current == 1:
                client.expire(redis_key, window)
            return current > maximum, current
        except Exception as exc:
            _mark_failure(exc)

    now = _now()
    memory_key = key
    with _memory_lock:
        _purge_memory()
        current, expires_at = _memory_counters.get(memory_key, (0, now + window))
        if expires_at <= now:
            current, expires_at = 0, now + window
        current += 1
        _memory_counters[memory_key] = (current, expires_at)
        _memory_counters.move_to_end(memory_key)
        while len(_memory_counters) > MAX_COUNTER_ENTRIES:
            _memory_counters.popitem(last=False)
        _stats["fallbacks"] += 1
    return current > maximum, current


def reset_counter(key: str) -> None:
    memory_key = key
    client = get_client()
    if client is not None:
        try:
            client.delete(_key(key))
        except Exception as exc:
            _mark_failure(exc)
    with _memory_lock:
        _memory_counters.pop(memory_key, None)


def current_counter(key: str) -> int:
    """Read a fixed-window counter without incrementing it."""
    client = get_client()
    if client is not None:
        try:
            payload = client.get(_key(key))
            return int(payload) if payload is not None else 0
        except Exception as exc:
            _mark_failure(exc)
    memory_key = key
    with _memory_lock:
        _purge_memory()
        current, expires_at = _memory_counters.get(memory_key, (0, 0.0))
        return int(current) if expires_at > _now() else 0


def health() -> dict[str, Any]:
    url = _redis_url()
    client = get_client() if url else None
    backend = "redis" if client is not None else "memory"
    status = "disabled"
    if url:
        status = "ok" if client is not None else "unavailable"
    return {
        "backend": backend,
        "configured": bool(url),
        "status": status,
        "prefix": _prefix(),
    }


def stats() -> dict[str, Any]:
    with _memory_lock:
        memory_entries = len(_memory_store)
        counters = len(_memory_counters)
        return {
            "hits": _stats["hits"],
            "misses": _stats["misses"],
            "stores": _stats["stores"],
            "fallbacks": _stats["fallbacks"],
            "memory_entries": memory_entries,
            "memory_counters": counters,
        }


def reset_for_tests() -> None:
    global _client, _failure_until, _logged_unavailable, _active_prefix
    with _client_lock:
        _client = None
        _failure_until = 0.0
        _logged_unavailable = False
    with _memory_lock:
        _memory_store.clear()
        _memory_counters.clear()
        _stats.update({"hits": 0, "misses": 0, "stores": 0, "fallbacks": 0})
    _active_prefix = None


def use_client_for_tests(client) -> None:
    """Inject a fake Redis client (for example fakeredis) in tests."""
    global _client, _failure_until, _logged_unavailable
    with _client_lock:
        _client = client
        _failure_until = 0.0
        _logged_unavailable = False
