"""Runtime request/app/session context helpers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI

from ..protocol.json_types import JSONObject
from ..security.authn import Principal
from ..tasks.engine import TaskContext


@dataclass
class AppContext:
    """Container for application-level services/config."""

    app: FastAPI


@dataclass
class SessionContext:
    """Container for session-level metadata."""

    session_id: str | None
    capabilities: JSONObject | None = None
    user: Principal | None = None


@dataclass
class RequestContext:
    """Per-call context passed to tools, optionally including task details."""

    app_context: AppContext
    session_context: SessionContext
    task_context: TaskContext | None = None

    @property
    def app(self) -> FastAPI:
        return self.app_context.app

    @property
    def session_id(self) -> str | None:
        return self.session_context.session_id


__all__ = ["AppContext", "RequestContext", "SessionContext"]
