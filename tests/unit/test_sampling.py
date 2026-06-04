"""Tests for the outbound sampling/createMessage request helper."""

import asyncio
import json

import pytest

from pymcp import create_app
from pymcp.capabilities.registry import ClientCapabilities
from pymcp.session.sampling import request_sampling
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


async def test_request_sampling_sends_correct_payload():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"sampling": {}})

    async def fake_client():
        raw = await session.queue.get()
        msg = json.loads(raw)
        assert msg["method"] == "sampling/createMessage"
        assert msg["params"]["maxTokens"] == 100
        response = {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "role": "assistant",
                "content": {"type": "text", "text": "Hello"},
                "model": "test-model",
                "stopReason": "endTurn",
            },
        }
        get_session_manager(app).resolve_pending_response(
            session.session_id, msg["id"], response,
        )

    client_task = asyncio.create_task(fake_client())
    result = await request_sampling(
        app,
        session.session_id,
        {
            "messages": [{"role": "user", "content": {"type": "text", "text": "Hi"}}],
            "maxTokens": 100,
        },
        timeout_seconds=5.0,
    )
    await client_task

    assert result["role"] == "assistant"
    assert result["model"] == "test-model"


async def test_request_sampling_raises_when_no_capability():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={})

    with pytest.raises(ValueError, match="does not support sampling"):
        await request_sampling(
            app,
            session.session_id,
            {"messages": [], "maxTokens": 50},
        )


async def test_request_sampling_tools_requires_sub_capability():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"sampling": {}})

    with pytest.raises(ValueError, match="does not support tool use"):
        await request_sampling(
            app,
            session.session_id,
            {
                "messages": [],
                "maxTokens": 50,
                "tools": [{"name": "get_weather", "description": "Weather", "inputSchema": {}}],
            },
        )


async def test_request_sampling_tools_accepted_with_sub_capability():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"sampling": {"tools": {}}})

    async def fake_client():
        raw = await session.queue.get()
        msg = json.loads(raw)
        assert msg["params"]["tools"] is not None
        response = {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "role": "assistant",
                "content": {"type": "text", "text": "result"},
                "model": "test-model",
            },
        }
        get_session_manager(app).resolve_pending_response(
            session.session_id, msg["id"], response,
        )

    client_task = asyncio.create_task(fake_client())
    result = await request_sampling(
        app,
        session.session_id,
        {
            "messages": [],
            "maxTokens": 50,
            "tools": [{"name": "get_weather", "description": "Weather", "inputSchema": {}}],
        },
        timeout_seconds=5.0,
    )
    await client_task
    assert result["role"] == "assistant"


async def test_request_sampling_timeout():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"sampling": {}})

    with pytest.raises(asyncio.TimeoutError):
        await request_sampling(
            app,
            session.session_id,
            {"messages": [], "maxTokens": 50},
            timeout_seconds=0.05,
        )


async def test_request_sampling_error_response():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"sampling": {}})

    async def fake_client():
        raw = await session.queue.get()
        msg = json.loads(raw)
        response = {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "error": {"code": -1, "message": "User rejected sampling request"},
        }
        get_session_manager(app).resolve_pending_response(
            session.session_id, msg["id"], response,
        )

    client_task = asyncio.create_task(fake_client())
    with pytest.raises(RuntimeError, match="Sampling error"):
        await request_sampling(
            app,
            session.session_id,
            {"messages": [], "maxTokens": 50},
            timeout_seconds=5.0,
        )
    await client_task
