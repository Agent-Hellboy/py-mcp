"""Cooperative shutdown for Streamable HTTP SSE connections."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, Literal

_SHUTDOWN_ATTR = "mcp_shutdown"

WaitOutcome = Literal["message", "timeout", "shutdown"]


def ensure_shutdown_event(app: Any) -> asyncio.Event:
    event = getattr(app.state, _SHUTDOWN_ATTR, None)
    if event is None:
        event = asyncio.Event()
        setattr(app.state, _SHUTDOWN_ATTR, event)
    return event


def is_shutting_down(app: Any) -> bool:
    event = getattr(app.state, _SHUTDOWN_ATTR, None)
    return event is not None and event.is_set()


async def wait_queue_message(
    queue: asyncio.Queue[str],
    *,
    shutdown: asyncio.Event | None,
    timeout: float,
) -> tuple[WaitOutcome, str | None]:
    if shutdown is not None and shutdown.is_set():
        return "shutdown", None

    get_task = asyncio.create_task(queue.get())
    tasks: set[asyncio.Task[object]] = {get_task}
    shutdown_task: asyncio.Task[object] | None = None
    if shutdown is not None:
        shutdown_task = asyncio.create_task(shutdown.wait())
        tasks.add(shutdown_task)

    try:
        done, pending = await asyncio.wait(
            tasks,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for task in pending:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    if shutdown is not None and shutdown.is_set():
        get_task.cancel()
        with suppress(asyncio.CancelledError):
            await get_task
        return "shutdown", None

    if get_task in done:
        return "message", get_task.result()

    get_task.cancel()
    with suppress(asyncio.CancelledError):
        await get_task
    return "timeout", None


__all__ = [
    "ensure_shutdown_event",
    "is_shutting_down",
    "wait_queue_message",
]
