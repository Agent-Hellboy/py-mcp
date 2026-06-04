"""Tests for send_log_message notification helper."""

import json

import pytest

from pymcp import create_app
from pymcp.session.notifications import send_log_message
from pymcp.session.store import get_session_manager
from pymcp.session.types import SessionState


pytestmark = pytest.mark.anyio


async def _ready_session(app):
    manager = get_session_manager(app)
    session = manager.create_session()
    await manager.mark_initialize_started(session.session_id)
    await manager.mark_initialized(session.session_id)
    session.stream_attached = True
    return session


async def test_send_log_message_basic():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)

    result = await send_log_message(
        app, session.session_id, level="info", logger="test.logger", data="hello"
    )
    assert result is True

    raw = session.queue.get_nowait()
    msg = json.loads(raw)
    assert msg["method"] == "notifications/message"
    assert msg["params"]["level"] == "info"
    assert msg["params"]["logger"] == "test.logger"
    assert msg["params"]["data"] == "hello"


async def test_send_log_message_without_optional_fields():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)

    result = await send_log_message(app, session.session_id, level="error")
    assert result is True

    raw = session.queue.get_nowait()
    msg = json.loads(raw)
    assert msg["params"]["level"] == "error"
    assert "logger" not in msg["params"]
    assert "data" not in msg["params"]


async def test_send_log_message_not_sent_to_non_ready_session():
    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()
    assert session.lifecycle_state == SessionState.WAIT_INIT

    result = await send_log_message(app, session.session_id, level="info")
    assert result is False


async def test_send_log_message_not_sent_without_stream():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)
    session.stream_attached = False

    result = await send_log_message(app, session.session_id, level="info")
    assert result is False
