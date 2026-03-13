"""Session types."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any


class SessionState(str, Enum):
    WAIT_INIT = "wait_init"
    WAIT_INITIALIZED = "wait_initialized"
    READY = "ready"
    CLOSED = "closed"


class SessionEvent(str, Enum):
    INITIALIZE = "initialize"
    CLIENT_READY = "client_ready"
    CLOSE = "close"


@dataclass(slots=True)
class Session:
    session_id: str
    queue: asyncio.Queue[str]
    initialized: bool = False
    client_ready: bool = False
    lifecycle_state: SessionState = SessionState.WAIT_INIT
    lifecycle_event: SessionEvent | None = None
    protocol_version: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    client_capabilities: dict[str, Any] = field(default_factory=dict)
    client_info: dict[str, Any] = field(default_factory=dict)
    stream_attached: bool = False
    attached_stream_id: str | None = None
    last_acked_event_id: str | None = None


__all__ = ["Session", "SessionEvent", "SessionState"]
