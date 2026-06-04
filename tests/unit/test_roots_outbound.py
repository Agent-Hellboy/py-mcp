"""Tests for the outbound roots/list request helper."""

import asyncio
import json

import pytest

from pymcp import create_app
from pymcp.capabilities.registry import ClientCapabilities
from pymcp.session.roots import request_roots_list
from pymcp.session.store import get_session_manager


pytestmark = pytest.mark.anyio


async def _init_session(app, *, client_caps=None):
    manager = get_session_manager(app)
    session = manager.create_session()
    if client_caps is not None:
        session.client_capabilities = ClientCapabilities(client_caps)
    await manager.mark_initialize_started(session.session_id)
    await manager.mark_initialized(session.session_id)
    return session


async def test_request_roots_list_sends_correct_payload():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"roots": {"listChanged": True}})

    async def fake_client():
        raw = await session.queue.get()
        msg = json.loads(raw)
        assert msg["method"] == "roots/list"
        assert "id" in msg
        response = {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "roots": [{"uri": "file:///workspace", "name": "My Project"}]
            },
        }
        manager = get_session_manager(app)
        manager.resolve_pending_response(session.session_id, msg["id"], response)

    client_task = asyncio.create_task(fake_client())
    roots = await request_roots_list(app, session.session_id, timeout_seconds=5.0)
    await client_task

    assert len(roots) == 1
    assert roots[0]["uri"] == "file:///workspace"
    assert roots[0]["name"] == "My Project"


async def test_request_roots_list_raises_when_no_capability():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={})

    with pytest.raises(ValueError, match="does not support roots"):
        await request_roots_list(app, session.session_id)


async def test_request_roots_list_raises_for_missing_session():
    app = create_app(middleware_config=None)

    with pytest.raises(ValueError, match="Session not found"):
        await request_roots_list(app, "nonexistent-session-id")


async def test_request_roots_list_timeout():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"roots": {}})

    with pytest.raises(asyncio.TimeoutError):
        await request_roots_list(app, session.session_id, timeout_seconds=0.05)
