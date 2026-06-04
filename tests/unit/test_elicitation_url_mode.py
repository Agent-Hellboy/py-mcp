"""Tests for URL mode elicitation."""

import asyncio
import json

import pytest

from pymcp import create_app
from pymcp.capabilities.registry import ClientCapabilities
from pymcp.session.elicitation import request_elicitation
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


async def test_url_mode_sends_correct_payload():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"elicitation": {"form": {}, "url": {}}})

    async def fake_client():
        raw = await session.queue.get()
        msg = json.loads(raw)
        assert msg["method"] == "elicitation/create"
        assert msg["params"]["mode"] == "url"
        assert msg["params"]["url"] == "https://example.com/auth"
        assert "elicitationId" in msg["params"]
        response = {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {"action": "accept"},
        }
        manager = get_session_manager(app)
        manager.resolve_pending_response(session.session_id, msg["id"], response)

    client_task = asyncio.create_task(fake_client())
    rpc_id, resp = await request_elicitation(
        app,
        session.session_id,
        {
            "mode": "url",
            "url": "https://example.com/auth",
            "message": "Please authorize",
        },
        timeout_seconds=5.0,
    )
    await client_task

    assert isinstance(rpc_id, str)
    assert resp["result"]["action"] == "accept"


async def test_url_mode_requires_url_parameter():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"elicitation": {"url": {}}})

    with pytest.raises(ValueError, match="requires a 'url' parameter"):
        await request_elicitation(
            app,
            session.session_id,
            {"mode": "url", "message": "Please authorize"},
        )


async def test_url_mode_generates_elicitation_id():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"elicitation": {"url": {}}})

    async def fake_client():
        raw = await session.queue.get()
        msg = json.loads(raw)
        assert "elicitationId" in msg["params"]
        response = {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {"action": "accept"},
        }
        get_session_manager(app).resolve_pending_response(
            session.session_id, msg["id"], response,
        )

    client_task = asyncio.create_task(fake_client())
    await request_elicitation(
        app,
        session.session_id,
        {
            "mode": "url",
            "url": "https://example.com/auth",
            "message": "Please authorize",
        },
        timeout_seconds=5.0,
    )
    await client_task
