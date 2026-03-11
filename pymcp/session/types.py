"""Session types."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    WAIT_INIT = "wait_init"
    READY = "ready"
    CLOSED = "closed"


@dataclass(slots=True)
class Session:
    session_id: str
    queue: asyncio.Queue[str]
    initialized: bool = False
    client_ready: bool = False
    lifecycle_state: SessionState = SessionState.WAIT_INIT
    protocol_version: str | None = None
    client_capabilities: dict[str, Any] = field(default_factory=dict)
    client_info: dict[str, Any] = field(default_factory=dict)


__all__ = ["Session", "SessionState"]
