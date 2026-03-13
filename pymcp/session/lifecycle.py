"""Session lifecycle state machine."""

from __future__ import annotations

import time
from typing import Callable

from .types import Session, SessionEvent, SessionState
from ..util.state_machine import AsyncStateMachine, Transition


_TRANSITIONS: dict[SessionState, dict[SessionEvent, Transition[SessionState, SessionEvent]]] = {
    SessionState.WAIT_INIT: {
        SessionEvent.INITIALIZE: Transition(SessionState.WAIT_INITIALIZED),
        SessionEvent.CLOSE: Transition(SessionState.CLOSED),
    },
    SessionState.WAIT_INITIALIZED: {
        SessionEvent.CLIENT_READY: Transition(SessionState.READY),
        SessionEvent.CLOSE: Transition(SessionState.CLOSED),
    },
    SessionState.READY: {
        SessionEvent.CLOSE: Transition(SessionState.CLOSED),
    },
    SessionState.CLOSED: {},
}


class SessionLifecycle:
    DEFAULT_HANDSHAKE_TIMEOUT = 30
    DEFAULT_IDLE_TIMEOUT = 600
    DEFAULT_RESUME_GRACE = 180

    def __init__(
        self,
        session: Session,
        *,
        handshake_timeout: int = DEFAULT_HANDSHAKE_TIMEOUT,
        idle_timeout: int = DEFAULT_IDLE_TIMEOUT,
        resume_grace: int = DEFAULT_RESUME_GRACE,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        self._handshake_timeout = handshake_timeout
        self._idle_timeout = idle_timeout
        self._resume_grace = resume_grace
        self._now = now_fn
        self.created_at = now_fn()
        self.last_activity = self.created_at

        def record_transition(
            _previous: SessionState,
            current: SessionState,
            event: SessionEvent,
            _name: str,
        ) -> None:
            self._session.lifecycle_state = current
            self._session.lifecycle_event = event

        self._machine = AsyncStateMachine(
            initial=SessionState.WAIT_INIT,
            transitions=_TRANSITIONS,
            name=f"session:{session.session_id}",
            on_any_transition=record_transition,
        )

        self._session.lifecycle_state = SessionState.WAIT_INIT
        self._session.lifecycle_event = None
        self._session.created_at = self.created_at
        self._session.last_activity = self.last_activity

    @property
    def state(self) -> SessionState:
        return self._machine.state

    def restore_state(self, state: SessionState) -> None:
        """Restore lifecycle to a specific state (e.g. when re-attaching a session)."""
        self._machine._state = state

    def touch(self) -> None:
        self.last_activity = self._now()
        self._session.last_activity = self.last_activity

    async def initialize(self) -> SessionState:
        self.touch()
        return await self._machine.trigger(SessionEvent.INITIALIZE)

    async def client_ready(self) -> SessionState:
        self.touch()
        return await self._machine.trigger(SessionEvent.CLIENT_READY)

    async def close(self) -> SessionState:
        return await self._machine.trigger(SessionEvent.CLOSE)

    @property
    def initialized(self) -> bool:
        return self.state in (SessionState.WAIT_INITIALIZED, SessionState.READY)

    @property
    def active(self) -> bool:
        return self.state == SessionState.READY

    def is_stale(self) -> bool:
        now = self._now()
        if self._idle_timeout and now - self.last_activity > self._idle_timeout:
            return True
        if not self.active and self._handshake_timeout and now - self.created_at > self._handshake_timeout:
            return True
        return False

    def can_resume(self) -> bool:
        if self.state == SessionState.CLOSED:
            return False
        return self._now() - self.last_activity <= self._resume_grace
