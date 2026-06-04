"""Tests for notifications/roots/list_changed handler."""

import pytest

from pymcp import create_app
from pymcp.capabilities.registry import ClientCapabilities
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.runtime.handlers.roots import on_roots_changed
from pymcp.session.store import get_session_manager


pytestmark = pytest.mark.anyio


async def _ready_session(app, *, client_caps=None):
    manager = get_session_manager(app)
    session = manager.create_session()
    if client_caps is not None:
        session.client_capabilities = ClientCapabilities(client_caps)
    await manager.mark_initialize_started(session.session_id)
    await manager.mark_initialized(session.session_id)
    return session


async def test_roots_list_changed_accepted():
    app = create_app(middleware_config=None)
    session = await _ready_session(app, client_caps={"roots": {"listChanged": True}})

    result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "method": "notifications/roots/list_changed"},
        app=app,
        direct_response=True,
    )
    assert result.status == 202


async def test_roots_list_changed_fires_callback():
    app = create_app(middleware_config=None)
    session = await _ready_session(app, client_caps={"roots": {"listChanged": True}})

    called_with = []

    def my_callback(cb_app, cb_session_id):
        called_with.append((cb_app, cb_session_id))

    on_roots_changed(my_callback)

    try:
        await process_jsonrpc_message(
            session.session_id,
            {"jsonrpc": "2.0", "method": "notifications/roots/list_changed"},
            app=app,
            direct_response=True,
        )

        assert len(called_with) >= 1
        assert called_with[-1] == (app, session.session_id)
    finally:
        from pymcp.runtime.handlers.roots import _roots_changed_callbacks
        if my_callback in _roots_changed_callbacks:
            _roots_changed_callbacks.remove(my_callback)
