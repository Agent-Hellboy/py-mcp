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
    progress_token: str | int | None = None

    @property
    def app(self) -> FastAPI:
        return self.app_context.app

    @property
    def session_id(self) -> str | None:
        return self.session_context.session_id

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        """Emit ``notifications/progress`` for the request's progress token.

        No-op when the client did not supply a ``_meta.progressToken``.
        """
        if not self.progress_token or self.session_id is None:
            return
        from ..session.notifications import send_notification
        from ..session.store import get_session_manager

        session = get_session_manager(self.app).get_session(self.session_id)
        if session is None:
            return
        params: JSONObject = {"progressToken": self.progress_token, "progress": progress}
        if total is not None:
            params["total"] = total
        if message is not None:
            params["message"] = message
        await send_notification(
            session,
            {"jsonrpc": "2.0", "method": "notifications/progress", "params": params},
        )


__all__ = ["AppContext", "RequestContext", "SessionContext"]
