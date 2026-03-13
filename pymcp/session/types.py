"""Session types."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any

from ..security.authn import Principal
from .events import EventLog


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
    principal: Principal | None = None
    initialized: bool = False
    client_ready: bool = False
    lifecycle_state: SessionState = SessionState.WAIT_INIT
    lifecycle_event: SessionEvent | None = None
    protocol_version: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    capabilities: dict[str, Any] | None = None
    client_capabilities: dict[str, Any] = field(default_factory=dict)
    client_info: dict[str, Any] = field(default_factory=dict)
    pending: dict[str, Any] = field(default_factory=dict)
    request_ids: set[str | int] = field(default_factory=set)
    resource_subscriptions: set[str] = field(default_factory=set)
    pending_elicitations: dict[str, asyncio.Future[dict[str, Any]]] = field(default_factory=dict)
    event_log: EventLog = field(default_factory=EventLog)
    streamable_streams: dict[str, asyncio.Queue[str]] = field(default_factory=dict)
    primary_streamable_stream_id: str | None = None
    stream_attached: bool = False
    attached_stream_id: str | None = None
    last_acked_event_id: str | None = None
    closed_at: float | None = None
    state_version: int = 0


__all__ = ["Session", "SessionEvent", "SessionState"]
