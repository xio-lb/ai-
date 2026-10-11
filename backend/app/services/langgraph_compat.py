"""Compatibility fixes for LangGraph's background task executor.

LangGraph runs node tasks through BackgroundExecutor and schedules the
follow-up checkpoint write from a Future done-callback. That callback can
fire while __exit__ is already shutting the thread pool down, so
ThreadPoolExecutor.submit raises
RuntimeError('cannot schedule new futures after shutdown') and the
checkpoint write is silently dropped. The same race exists in the asyncio
variant when the event loop is closing.

Left in place, the regression surfaces as intermittent checkpoint loss: a
repeated graph invocation re-runs nodes it should have reused. This module
keeps the follow-up work by running the submitted callable inline when the
executor or loop is already going away.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from langgraph.pregel import _executor

logger = logging.getLogger(__name__)

_PATCH_MARKER = "_travel_planner_shutdown_safe"


def install_shutdown_safe_executor() -> None:
    """Make LangGraph drop no writes when its executor closes mid-flight."""

    if getattr(_executor, _PATCH_MARKER, False):
        return

    original_sync_submit = _executor.BackgroundExecutor.submit

    def safe_sync_submit(self: Any, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return original_sync_submit(self, fn, *args, **kwargs)
        except RuntimeError as exc:
            if "shutdown" not in str(exc):
                raise
            logger.debug("LangGraph thread pool already shutting down; running task inline")
            return fn(*args, **kwargs)

    original_async_submit = _executor.AsyncBackgroundExecutor.submit

    def safe_async_submit(self: Any, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return original_async_submit(self, fn, *args, **kwargs)
        except RuntimeError as exc:
            message = str(exc)
            if "event loop is closed" not in message and "loop is closed" not in message:
                raise
            logger.debug("LangGraph event loop already closed; running task inline")
            result = fn(*args, **kwargs)
            if hasattr(result, "close"):
                result.close()
            return result

    _executor.BackgroundExecutor.submit = safe_sync_submit
    _executor.AsyncBackgroundExecutor.submit = safe_async_submit
    setattr(_executor, _PATCH_MARKER, True)
