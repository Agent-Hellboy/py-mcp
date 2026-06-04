"""Tests for completion/complete handler."""

import pytest

from pymcp import create_app
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.store import get_session_manager
from pymcp.settings import CapabilitySettings, ServerSettings


pytestmark = pytest.mark.anyio


async def _ready_session(app):
    manager = get_session_manager(app)
    session = manager.create_session()
    await manager.mark_initialize_started(session.session_id)
    await manager.mark_initialized(session.session_id)
    return session


async def test_completions_gated_when_disabled():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=False)
        ),
    )
    session = await _ready_session(app)

    result = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/prompt", "name": "test"},
                "argument": {"name": "topic", "value": "wea"},
            },
        },
        app=app,
        direct_response=True,
    )
    assert result.status == 200
    assert result.payload["error"]["code"] == -32601
    assert "completions not supported" in result.payload["error"]["message"]


async def test_completions_returns_empty_when_enabled():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/prompt", "name": "test"},
                "argument": {"name": "topic", "value": "wea"},
            },
        },
        app=app,
        direct_response=True,
    )
    assert result.status == 200
    completion = result.payload["result"]["completion"]
    assert isinstance(completion["values"], list)
    assert completion["hasMore"] is False


async def test_completions_rejects_missing_ref():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "completion/complete",
            "params": {"argument": {"name": "topic", "value": "wea"}},
        },
        app=app,
        direct_response=True,
    )
    assert result.payload["error"]["code"] == -32602


async def test_completions_rejects_missing_argument():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "completion/complete",
            "params": {"ref": {"type": "ref/prompt", "name": "test"}},
        },
        app=app,
        direct_response=True,
    )
    assert result.payload["error"]["code"] == -32602
