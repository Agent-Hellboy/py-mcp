import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.security import TokenMapAuthenticator
from pymcp.session import get_session_store
from pymcp.transport.streamable_http import _stream_session_events


pytestmark = pytest.mark.anyio


class _FakeRequest:
    def __init__(self, app):
        self.app = app
        self._disconnect = False

    async def is_disconnected(self) -> bool:
        return self._disconnect

    def disconnect(self) -> None:
        self._disconnect = True


async def test_stream_generator_emits_connected_and_message():
    app = create_app(middleware_config=None)
    manager = get_session_store(app)
    session = manager.create_session()
    request = _FakeRequest(app)

    await manager.note_stream_open(session.session_id, stream_id="stream-1")
    session.queue.put_nowait(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})
    )

    stream = _stream_session_events(request, session.session_id, session, "stream-1")
    assert await anext(stream) == ": connected\n\n"

    event = await anext(stream)
    assert "event: message" in event
    assert '"notifications/tools/list_changed"' in event

    request.disconnect()
    await stream.aclose()
    assert session.stream_attached is False


async def test_stream_generator_emits_ping_when_idle():
    app = create_app(middleware_config=None)
    manager = get_session_store(app)
    session = manager.create_session()
    request = _FakeRequest(app)

    await manager.note_stream_open(session.session_id, stream_id="stream-1")
    stream = _stream_session_events(
        request,
        session.session_id,
        session,
        "stream-1",
        heartbeat_interval=0.01,
    )
    assert await anext(stream) == ": connected\n\n"

    ping = await asyncio.wait_for(anext(stream), timeout=1.0)
    assert ping == ": ping\n\n"

    request.disconnect()
    await stream.aclose()


def test_streamable_http_preserves_session_principal_and_rejects_mismatch():
    app = create_app(
        middleware_config=None,
        authn=TokenMapAuthenticator(
            {
                "alice-token": {"subject": "alice"},
                "bob-token": {"subject": "bob"},
            }
        ),
    )
    client = TestClient(app)

    initialize = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer alice-token",
        },
    )
    assert initialize.status_code == 200
    session_id = initialize.headers["MCP-Session-Id"]

    follow_up = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
        headers={
            "Accept": "application/json, text/event-stream",
            "MCP-Session-Id": session_id,
        },
    )
    assert follow_up.status_code == 200

    session = get_session_store(app).get_session(session_id)
    assert session is not None
    assert session.principal is not None
    assert session.principal.subject == "alice"

    mismatched = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "ping"},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer bob-token",
            "MCP-Session-Id": session_id,
        },
    )
    assert mismatched.status_code == 403
    assert mismatched.json()["error"]["message"] == "Session principal mismatch"
