from typing import Annotated, TypedDict

import operator
from langgraph.graph import END, START, StateGraph

from app.services.graph_checkpoint import SyncMemorySaver


class CounterState(TypedDict):
    count: Annotated[int, operator.add]
    done: bool


def _build(saver, calls):
    def first_node(state):
        return {"count": 1}

    def second_node(state):
        if calls["fail"]:
            calls["fail"] = False
            raise RuntimeError("transient failure")
        return {"done": True}

    graph = StateGraph(CounterState)
    graph.add_node("first", first_node)
    graph.add_node("second", second_node)
    graph.add_edge(START, "first")
    graph.add_edge("first", "second")
    graph.add_edge("second", END)
    return graph.compile(checkpointer=saver)


def test_sync_memory_saver_resumes_failed_run():
    saver = SyncMemorySaver()
    app = _build(saver, {"fail": True})
    config = {"configurable": {"thread_id": "run-a"}}

    try:
        app.invoke({"count": 0, "done": False}, config)
    except RuntimeError:
        pass

    # The failed run left a checkpoint whose next node is still pending.
    assert app.get_state(config).next == ("second",)

    app.invoke(None, config)
    state = app.get_state(config)
    assert state.next == ()
    assert state.values["count"] == 1
    assert state.values["done"] is True
    assert saver.get_tuple(config) is not None


def test_sync_memory_saver_isolates_threads():
    saver = SyncMemorySaver()
    app = _build(saver, {"fail": False})
    config_a = {"configurable": {"thread_id": "run-a"}}
    config_b = {"configurable": {"thread_id": "run-b"}}

    app.invoke({"count": 1, "done": False}, config_a)
    app.invoke({"count": 5, "done": False}, config_b)

    assert app.get_state(config_a).values["count"] == 2
    assert app.get_state(config_b).values["count"] == 6
    assert saver.get_tuple(config_a) is not None
    assert saver.get_tuple(config_b) is not None