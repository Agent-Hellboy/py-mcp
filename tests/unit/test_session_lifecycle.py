import asyncio

import pytest

from pymcp.session.lifecycle import SessionState
from pymcp.session.store import SessionManager


pytestmark = pytest.mark.anyio("asyncio")


async def test_session_lifecycle_reaches_ready_after_handshake():
    manager = SessionManager(handshake_timeout=30, idle_timeout=30, resume_grace=30)
    session = manager.create_session()
    assert session.lifecycle_state == SessionState.WAIT_INIT

    await manager.mark_initialize_started(session.session_id)
    assert session.lifecycle_state == SessionState.WAIT_INITIALIZED

    await manager.mark_initialized(session.session_id)
    assert session.lifecycle_state == SessionState.READY
    assert session.initialized is True


async def test_session_handshake_timeout_triggers_cleanup():
    manager = SessionManager(handshake_timeout=1, idle_timeout=100, resume_grace=10)
    session = manager.create_session()
    lifecycle = manager._get_lifecycle(session.session_id)  # pylint: disable=protected-access
    lifecycle.created_at -= 5

    assert manager.get_session(session.session_id) is None
    await asyncio.sleep(0)
    assert manager.session_exists(session.session_id) is False


async def test_session_idle_timeout_triggers_cleanup():
    manager = SessionManager(handshake_timeout=100, idle_timeout=1, resume_grace=10)
    session = manager.create_session()
    lifecycle = manager._get_lifecycle(session.session_id)  # pylint: disable=protected-access
    lifecycle.last_activity -= 5

    assert manager.get_session(session.session_id) is None
    await asyncio.sleep(0)
    assert manager.session_exists(session.session_id) is False
