"""Progress reporting bridge between stream endpoints and agents."""

import contextvars
from typing import Any, Callable

_progress_callback: contextvars.ContextVar[Callable[[str], None] | None] = (
    contextvars.ContextVar("progress_callback", default=None)
)


def set_progress_callback(callback: Callable[[str], None]) -> Any:
    return _progress_callback.set(callback)


def reset_progress_callback(token: Any) -> None:
    _progress_callback.reset(token)


def report_progress(message: str) -> None:
    callback = _progress_callback.get()
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        pass
