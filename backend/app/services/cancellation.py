"""Cancellation checks shared between async tasks and the LangGraph nodes. 

A context var keeps the call sites clean: agents only ask "should I stop?", and
the API layer decides whether the answer comes from a task row, a timeout or a
client disconnect.
"""
from __future__ import annotations

from typing import Callable

import contextvars

_cancel_check: contextvars.ContextVar[Callable[[], bool] | None] = contextvars.ContextVar(
    "cancel_check", default=None
)


class TaskCancelled(Exception):
    """Raised by nodes when the owning task has been cancelled."""


def set_cancel_check(check: Callable[[], bool] | None):
    return _cancel_check.set(check)


def reset_cancel_check(token) -> None:
    _cancel_check.reset(token)


def raise_if_cancelled() -> None:
    check = _cancel_check.get()
    if check is not None and check():
        raise TaskCancelled("任务已取消")
