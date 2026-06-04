"""Tests for elicitation capability gating."""

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


async def test_form_mode_rejected_when_client_lacks_elicitation():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={})

    with pytest.raises(ValueError, match="does not support elicitation"):
        await request_elicitation(
            app,
            session.session_id,
            {"mode": "form", "message": "Need info"},
        )


async def test_url_mode_rejected_when_client_only_supports_form():
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"elicitation": {"form": {}}})

    with pytest.raises(ValueError, match="does not support elicitation mode 'url'"):
        await request_elicitation(
            app,
            session.session_id,
            {"mode": "url", "url": "https://example.com/auth", "message": "Auth needed"},
        )


async def test_form_mode_accepted_with_empty_elicitation_dict():
    """Per spec, empty elicitation {} means form-only support."""
    app = create_app(middleware_config=None)
    session = await _init_session(app, client_caps={"elicitation": {}})

    # Should not raise -- but will time out since no client is listening
    import asyncio

    with pytest.raises(asyncio.TimeoutError):
        await request_elicitation(
            app,
            session.session_id,
            {"mode": "form", "message": "Need info"},
            timeout_seconds=0.05,
        )
