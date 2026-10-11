"""Regression test for the LangGraph executor shutdown race.

LangGraph schedules a node's follow-up checkpoint write from a future
done-callback. If the executor is already shutting down, that write used to
raise RuntimeError and be dropped. The compatibility patch must run it inline
instead, so checkpointing survives the shutdown race.
"""
from concurrent.futures import ThreadPoolExecutor

from langgraph.pregel import _executor

from app.services.langgraph_compat import install_shutdown_safe_executor


def test_sync_submit_runs_inline_after_executor_shutdown():
    install_shutdown_safe_executor()

    executor = object.__new__(_executor.BackgroundExecutor)
    pool = ThreadPoolExecutor(max_workers=1)
    pool.shutdown(wait=True)
    executor.executor = pool
    executor.tasks = {}

    def inline(fn, *args, **kwargs):
        kwargs.pop("__name__", None)
        kwargs.pop("__cancel_on_exit__", None)
        kwargs.pop("__reraise_on_exit__", None)
        kwargs.pop("__next_tick__", None)
        return fn(*args, **kwargs)

    executor.submit = inline
    result = _executor.BackgroundExecutor.submit(executor, lambda value: value + 1, 41)

    assert result == 42
