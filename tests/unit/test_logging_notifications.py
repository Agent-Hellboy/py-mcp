"""Tests for logging/setLevel and send_log_message notification helper."""

import json

import pytest

from pymcp import create_app
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.notifications import send_log_message
from pymcp.session.store import get_session_manager
from pymcp.session.types import SessionState
from pymcp.settings import CapabilitySettings, ServerSettings


pytestmark = pytest.mark.anyio


def _logging_app():
    return create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(logging_enabled=True),
        ),
    )


async def _ready_session(app):
    manager = get_session_manager(app)
    session = manager.create_session()
    await manager.mark_initialize_started(session.session_id)
    await manager.mark_initialized(session.session_id)
    session.stream_attached = True
    return session


async def _initialize_session(app):
    manager = get_session_manager(app)
    session = manager.create_session()
    await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        },
        app=app,
        direct_response=True,
    )
    await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        app=app,
        direct_response=True,
    )
    await manager.note_stream_open(session.session_id, stream_id="stream-1")
    return session


async def test_send_log_message_basic():
    app = _logging_app()
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
    app = _logging_app()
    session = await _ready_session(app)

    result = await send_log_message(app, session.session_id, level="error")
    assert result is True

    raw = session.queue.get_nowait()
    msg = json.loads(raw)
    assert msg["params"]["level"] == "error"
    assert "logger" not in msg["params"]
    assert "data" not in msg["params"]


async def test_send_log_message_not_sent_to_non_ready_session():
    app = _logging_app()
    manager = get_session_manager(app)
    session = manager.create_session()
    assert session.lifecycle_state == SessionState.WAIT_INIT

    result = await send_log_message(app, session.session_id, level="info")
    assert result is False


async def test_send_log_message_not_sent_without_stream():
    app = _logging_app()
    session = await _ready_session(app)
    session.stream_attached = False

    result = await send_log_message(app, session.session_id, level="info")
    assert result is False


async def test_send_log_message_requires_logging_capability():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)

    result = await send_log_message(app, session.session_id, level="info")
    assert result is False


async def test_logging_set_level():
    app = _logging_app()
    session = await _initialize_session(app)

    response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "logging/setLevel",
            "params": {"level": "warning"},
        },
        app=app,
        direct_response=True,
    )
    assert response.payload["result"] == {}
    assert session.log_level == "warning"


async def test_logging_set_level_rejects_invalid_level():
    app = _logging_app()
    session = await _initialize_session(app)

    response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "logging/setLevel",
            "params": {"level": "verbose"},
        },
        app=app,
        direct_response=True,
    )
    assert response.payload["error"]["code"] == -32602


async def test_logging_set_level_filters_notifications():
    app = _logging_app()
    session = await _initialize_session(app)

    await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "logging/setLevel",
            "params": {"level": "error"},
        },
        app=app,
        direct_response=True,
    )

    assert await send_log_message(app, session.session_id, level="info") is False
    assert await send_log_message(app, session.session_id, level="error") is True

    raw = session.queue.get_nowait()
    msg = json.loads(raw)
    assert msg["params"]["level"] == "error"


async def test_logging_set_level_not_supported_when_capability_disabled():
    app = create_app(middleware_config=None)
    session = await _initialize_session(app)

    response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "logging/setLevel",
            "params": {"level": "info"},
        },
        app=app,
        direct_response=True,
    )
    assert response.payload["error"]["code"] == -32601
