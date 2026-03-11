import asyncio
import json

import pytest

from pymcp import create_app
from pymcp.session import get_session_store
from pymcp.transport.streamable_http import _stream_session_events


pytestmark = pytest.mark.anyio("asyncio")


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
