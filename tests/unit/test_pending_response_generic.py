"""Tests for the unified pending request/response mechanism."""

import asyncio

import pytest

from pymcp import create_app
from pymcp.session.store import get_session_manager


pytestmark = pytest.mark.anyio


async def _ready_session(app):
    manager = get_session_manager(app)
    session = manager.create_session()
    await manager.mark_initialize_started(session.session_id)
    await manager.mark_initialized(session.session_id)
    return session


async def test_register_and_resolve_pending_request():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)
    manager = get_session_manager(app)

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    manager.register_pending_request(session.session_id, "req-1", fut)

    payload = {"jsonrpc": "2.0", "id": "req-1", "result": {"data": "hello"}}
    resolved = manager.resolve_pending_response(session.session_id, "req-1", payload)

    assert resolved is True
    assert fut.done()
    assert fut.result() == payload


async def test_resolve_unknown_rpc_id_returns_false():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)
    manager = get_session_manager(app)

    resolved = manager.resolve_pending_response(
        session.session_id, "nonexistent", {"jsonrpc": "2.0", "id": "nonexistent"}
    )
    assert resolved is False


async def test_resolve_unknown_session_returns_false():
    app = create_app(middleware_config=None)
    manager = get_session_manager(app)

    resolved = manager.resolve_pending_response(
        "no-such-session", "req-1", {"jsonrpc": "2.0", "id": "req-1"}
    )
    assert resolved is False


async def test_resolve_already_done_future_returns_false():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)
    manager = get_session_manager(app)

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    fut.set_result({"already": "done"})
    manager.register_pending_request(session.session_id, "req-2", fut)

    resolved = manager.resolve_pending_response(
        session.session_id, "req-2", {"jsonrpc": "2.0", "id": "req-2"}
    )
    assert resolved is False


async def test_cleanup_cancels_pending_requests():
    app = create_app(middleware_config=None)
    session = await _ready_session(app)
    manager = get_session_manager(app)

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    manager.register_pending_request(session.session_id, "req-3", fut)

    await manager.cleanup_session(session.session_id)
    assert fut.cancelled()


async def test_fallback_to_legacy_elicitation_futures():
    """resolve_pending_response should fall back to pending_elicitations."""
    app = create_app(middleware_config=None)
    session = await _ready_session(app)
    manager = get_session_manager(app)

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    manager.register_elicitation_future(session.session_id, "elic-1", fut)

    payload = {"jsonrpc": "2.0", "id": "elic-1", "result": {"action": "accept"}}
    resolved = manager.resolve_pending_response(session.session_id, "elic-1", payload)

    assert resolved is True
    assert fut.done()
    assert fut.result() == payload
