"""Synchronous in-process checkpointer for the LangGraph workflow.

LangGraph's stock ``InMemorySaver`` routes checkpoint writes through a thread
pool executor. In this single-instance deployment that adds ordering races at
interpreter shutdown without buying anything, so this saver reuses the same
storage but keeps the async hooks synchronous. The public behaviour is still a
checkpointer keyed by ``thread_id``: runs can resume, and generation variants
cannot see each other's state.
"""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any, Iterator, Sequence

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.services.langgraph_compat import install_shutdown_safe_executor

install_shutdown_safe_executor()


APP_CHECKPOINT_TYPES = [
    "app.schemas.trip.TripRequest",
    "app.schemas.trip.TripPlan",
    "app.schemas.trip.AttractionCandidate",
    "app.schemas.trip.FoodCandidate",
    "app.schemas.trip.HotelCandidate",
    "app.schemas.trip.WeatherInfo",
]


class SyncMemorySaver(
    BaseCheckpointSaver[str], AbstractContextManager, AbstractAsyncContextManager
):
    """In-memory checkpointer whose async surface delegates synchronously."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        serializer = JsonPlusSerializer().with_msgpack_allowlist(APP_CHECKPOINT_TYPES)
        self._store = InMemorySaver(serde=serializer)

    def __getattr__(self, name: str) -> Any:
        # Delegate optional checkpoint hooks (versioning, thread cleanup) to the
        # battle-tested in-memory implementation.
        return getattr(self._store, name)

    def __enter__(self):
        return self._store.__enter__()

    def __exit__(self, *args: Any):
        return self._store.__exit__(*args)

    async def __aenter__(self):
        return await self._store.__aenter__()

    async def __aexit__(self, *args: Any):
        return await self._store.__aexit__(*args)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self._store.get_tuple(config)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        return self._store.list(config, filter=filter, before=before, limit=limit)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self._store.put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return self._store.put_writes(config, writes, task_id, task_path)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> list[CheckpointTuple]:
        return list(self.list(config, filter=filter, before=before, limit=limit))

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)
