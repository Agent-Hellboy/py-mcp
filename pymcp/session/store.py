"""Application-scoped session manager."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from uuid import uuid4

from .lifecycle import SessionLifecycle
from .queueing import get_session_outbound_queue, safe_queue_put
from .types import Session, SessionState


class SessionManager:
    def __init__(
        self,
        *,
        handshake_timeout: int = SessionLifecycle.DEFAULT_HANDSHAKE_TIMEOUT,
        idle_timeout: int = SessionLifecycle.DEFAULT_IDLE_TIMEOUT,
        resume_grace: int = SessionLifecycle.DEFAULT_RESUME_GRACE,
        now_fn=time.monotonic,
    ) -> None:
        self._sessions: dict[str, Session] = {}
        self._lifecycles: dict[str, SessionLifecycle] = {}
        self._handshake_timeout = handshake_timeout
        self._idle_timeout = idle_timeout
        self._resume_grace = resume_grace
        self._now = now_fn

    def _build_lifecycle(self, session: Session) -> SessionLifecycle:
        return SessionLifecycle(
            session,
            handshake_timeout=self._handshake_timeout,
            idle_timeout=self._idle_timeout,
            resume_grace=self._resume_grace,
            now_fn=self._now,
        )

    def create_session(self) -> Session:
        session = Session(session_id=str(uuid4()), queue=asyncio.Queue())
        self._sessions[session.session_id] = session
        self._lifecycles[session.session_id] = self._build_lifecycle(session)
        return session

    def create(self) -> Session:
        return self.create_session()

    def attach_session(self, session: Session) -> Session:
        self._sessions[session.session_id] = session
        lifecycle = self._build_lifecycle(session)
        lifecycle.created_at = session.created_at
        lifecycle.last_activity = session.last_activity
        lifecycle.restore_state(session.lifecycle_state)
        self._lifecycles[session.session_id] = lifecycle
        return session

    def get_session(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        lifecycle = self._lifecycles.get(session_id)
        if session is None or lifecycle is None:
            return None
        if lifecycle.is_stale():
            try:
                asyncio.get_running_loop().create_task(self.cleanup_session(session_id))
            except RuntimeError:
                self._sessions.pop(session_id, None)
                self._lifecycles.pop(session_id, None)
            return None
        lifecycle.touch()
        return session

    def list_sessions(self) -> list[Session]:
        return list(self._sessions.values())

    def session_exists(self, session_id: str) -> bool:
        return self.get_session(session_id) is not None

    def _get_lifecycle(self, session_id: str) -> SessionLifecycle | None:
        return self._lifecycles.get(session_id)

    async def mark_initialize_started(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        lifecycle = self._lifecycles.get(session_id)
        if session is None or lifecycle is None:
            return
        await lifecycle.initialize()
        session.lifecycle_state = lifecycle.state

    async def mark_initialized(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        lifecycle = self._lifecycles.get(session_id)
        if session is None or lifecycle is None:
            return
        await lifecycle.client_ready()
        session.lifecycle_state = lifecycle.state
        session.initialized = True
        session.client_ready = True

    async def mark_client_ready(self, session_id: str) -> None:
        await self.mark_initialized(session_id)

    async def note_stream_open(
        self,
        session_id: str,
        stream_id: str | None = None,
        last_event_id: str | None = None,
    ) -> None:
        session = self._sessions.get(session_id)
        lifecycle = self._lifecycles.get(session_id)
        if session is None or lifecycle is None:
            return
        session.stream_attached = True
        session.attached_stream_id = stream_id or session.attached_stream_id
        session.last_acked_event_id = last_event_id or session.last_acked_event_id
        lifecycle.touch()

    def mark_stream_detached(self, session_id: str, stream_id: str | None = None) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        if stream_id is None or session.attached_stream_id == stream_id:
            session.stream_attached = False
            session.attached_stream_id = None

    async def cleanup_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        lifecycle = self._lifecycles.get(session_id)
        if session is None or lifecycle is None:
            return
        await lifecycle.close()
        session.lifecycle_state = SessionState.CLOSED
        for future in session.pending_elicitations.values():
            if not future.done():
                future.cancel()
        self._sessions.pop(session_id, None)
        self._lifecycles.pop(session_id, None)

    async def close_session(self, session_id: str) -> Session | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        await self.cleanup_session(session_id)
        return session

    def register_elicitation_future(
        self,
        session_id: str,
        rpc_id: str,
        future: asyncio.Future[dict[str, Any]],
    ) -> None:
        """Track a pending elicitation future for a session."""

        session = self._sessions.get(session_id)
        if session is not None:
            session.pending_elicitations[rpc_id] = future

    def resolve_elicitation_response(
        self,
        session_id: str,
        rpc_id: str,
        payload: dict[str, Any],
    ) -> bool:
        """Resolve a pending elicitation for a specific session."""

        session = self._sessions.get(session_id)
        if session is None:
            return False
        future = session.pending_elicitations.pop(rpc_id, None)
        if future is None or future.done():
            return False
        future.set_result(payload)
        return True

    def resolve_elicitation_response_any(
        self,
        rpc_id: str,
        payload: dict[str, Any],
    ) -> bool:
        """Resolve a pending elicitation by searching all active sessions."""

        for session in self._sessions.values():
            future = session.pending_elicitations.get(rpc_id)
            if future is None or future.done():
                continue
            session.pending_elicitations.pop(rpc_id, None)
            future.set_result(payload)
            return True
        return False

    def subscribe_resource(self, session_id: str, uri: str) -> bool:
        """Subscribe a session to a resource URI."""

        session = self._sessions.get(session_id)
        if session is None:
            return False
        session.resource_subscriptions.add(uri)
        return True

    def unsubscribe_resource(self, session_id: str, uri: str) -> bool:
        """Unsubscribe a session from a resource URI."""

        session = self._sessions.get(session_id)
        if session is None:
            return False
        removed = uri in session.resource_subscriptions
        session.resource_subscriptions.discard(uri)
        return removed

    def broadcast_resource_update(self, uri: str, notification: dict[str, Any]) -> None:
        """Broadcast a resource update to sessions subscribed to the URI."""

        message = json.dumps(notification)
        for session in self._sessions.values():
            if session.lifecycle_state != SessionState.READY or not session.stream_attached:
                continue
            if uri in session.resource_subscriptions:
                safe_queue_put(get_session_outbound_queue(session), message)

    def broadcast_notification(self, notification: dict[str, Any]) -> None:
        """Broadcast a notification to all ready sessions with an attached stream."""

        message = json.dumps(notification)
        for session in self._sessions.values():
            if session.lifecycle_state != SessionState.READY or not session.stream_attached:
                continue
            safe_queue_put(get_session_outbound_queue(session), message)


def get_session_manager(app: Any) -> SessionManager:
    if not hasattr(app.state, "session_manager"):
        app.state.session_manager = SessionManager()
    return app.state.session_manager


def get_session_store(app: Any) -> SessionManager:
    return get_session_manager(app)


__all__ = ["SessionManager", "get_session_manager", "get_session_store"]
