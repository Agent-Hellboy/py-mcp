"""Application-scoped session manager."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from .types import Session, SessionState


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> Session:
        session = Session(session_id=str(uuid4()), queue=asyncio.Queue())
        self._sessions[session.session_id] = session
        return session

    def create(self) -> Session:
        return self.create_session()

    def attach_session(self, session: Session) -> Session:
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def mark_initialized(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.initialized = True
        session.lifecycle_state = SessionState.READY

    def mark_client_ready(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.client_ready = True

    def close_session(self, session_id: str) -> Session | None:
        session = self._sessions.pop(session_id, None)
        if session is not None:
            session.lifecycle_state = SessionState.CLOSED
        return session


def get_session_manager(app: Any) -> SessionManager:
    if not hasattr(app.state, "session_manager"):
        app.state.session_manager = SessionManager()
    return app.state.session_manager


def get_session_store(app: Any) -> SessionManager:
    return get_session_manager(app)


__all__ = ["SessionManager", "get_session_manager", "get_session_store"]
