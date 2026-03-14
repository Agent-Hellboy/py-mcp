"""Session queue selection and non-blocking enqueue helpers."""

from __future__ import annotations

import asyncio

from .types import Session


def get_session_outbound_queue(session: Session) -> asyncio.Queue[str]:
    """Return the outbound queue used for server-to-client messages."""

    return session.queue


def safe_queue_put(queue: asyncio.Queue[str] | None, msg: str) -> bool:
    """Put onto a queue without blocking; return False when backpressure wins."""

    if not queue:
        return False
    try:
        queue.put_nowait(msg)
    except (asyncio.QueueFull, RuntimeError):
        return False
    return True
