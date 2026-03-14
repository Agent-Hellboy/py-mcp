"""Cancellation support for long-running PyMCP operations."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, cast
from uuid import uuid4

from fastapi import FastAPI


CancellationCallback = Callable[[], None | Awaitable[None]]


async def _await_cancellation_callback(outcome: Awaitable[None]) -> None:
    await outcome


class CancellationManager:
    """Tracks cancelled request IDs and optional callbacks."""

    def __init__(self) -> None:
        self._cancelled_requests: set[str] = set()
        self._cancellation_callbacks: dict[str, CancellationCallback] = {}
        self._cancelled_reasons: dict[str, str | None] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._cleared_requests: set[str] = set()

    def create_token(self, request_id: Any = None) -> str:
        """Create a normalized cancellation token for a request ID."""

        if request_id is None or isinstance(request_id, bool):
            return str(uuid4())
        token = str(request_id)
        token = token or str(uuid4())
        self._cancelled_requests.discard(token)
        self._cancellation_callbacks.pop(token, None)
        self._cancelled_reasons.pop(token, None)
        self._cleared_requests.discard(token)
        event = self._cancel_events.get(token)
        if event is not None and event.is_set():
            self._cancel_events[token] = asyncio.Event()
        return token

    def register_callback(self, token: str, callback: CancellationCallback) -> None:
        """Register a callback to run when the token is cancelled."""

        self._cancellation_callbacks[token] = callback

    def cancel(self, token: str, reason: str | None = None) -> bool:
        """Cancel a token and notify any waiter or callback."""

        if token in self._cancelled_requests:
            return True

        self._cancelled_requests.add(token)
        self._cancelled_reasons[token] = reason
        self._cleared_requests.discard(token)
        event = self._cancel_events.get(token)
        if event is not None:
            event.set()

        callback = self._cancellation_callbacks.pop(token, None)
        if callback:
            try:
                outcome = callback()
                if outcome is not None and asyncio.iscoroutine(outcome):
                    asyncio.create_task(_await_cancellation_callback(outcome))
            except Exception:
                return True
        return True

    def is_cancelled(self, token: str) -> bool:
        """Return True when the token has been cancelled."""

        return token in self._cancelled_requests

    def clear(self, token: str) -> None:
        """Clear cancellation state for a completed request."""

        self._cancelled_requests.discard(token)
        self._cancellation_callbacks.pop(token, None)
        self._cancelled_reasons.pop(token, None)
        self._cleared_requests.add(token)
        event = self._cancel_events.get(token)
        if event is None:
            event = asyncio.Event()
            self._cancel_events[token] = event
        event.set()

    async def wait(self, token: str) -> bool:
        """Wait until a token is cancelled or cleared."""

        if self.is_cancelled(token):
            return True
        if token in self._cleared_requests:
            return False
        event = self._cancel_events.get(token)
        if event is None:
            event = asyncio.Event()
            self._cancel_events[token] = event
            if self.is_cancelled(token):
                event.set()
                return True
        await event.wait()
        return self.is_cancelled(token)


class CancellationToken:
    """A lightweight view over a token stored in a CancellationManager."""

    def __init__(self, token: str, manager: CancellationManager):
        self.token = token
        self.manager = manager

    def is_cancelled(self) -> bool:
        """Return True if this token has been cancelled."""

        return self.manager.is_cancelled(self.token)

    def check_cancelled(self) -> None:
        """Raise CancelledError if the request has been cancelled."""

        if self.is_cancelled():
            raise CancelledError(f"Request cancelled: {self.token}")

    async def wait(self) -> bool:
        """Wait until the token is cancelled or cleared."""

        return await self.manager.wait(self.token)


class CancelledError(Exception):
    """Raised when cooperative cancellation is observed."""


def get_cancellation_manager(app: FastAPI) -> CancellationManager:
    """Return the app-scoped CancellationManager."""

    if not hasattr(app.state, "cancellation_manager"):
        app.state.cancellation_manager = CancellationManager()
    return cast(CancellationManager, app.state.cancellation_manager)
