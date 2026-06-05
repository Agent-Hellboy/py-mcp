import json

import pytest

from pymcp import create_app
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


async def _collect_events(stream, *, limit: int = 5) -> list[str]:
    events: list[str] = []
    async for event in stream:
        events.append(event)
        if len(events) >= limit:
            break
    return events


async def test_stream_replays_missed_events_after_last_event_id():
    app = create_app(middleware_config=None)
    manager = get_session_store(app)
    session = manager.create_session()
    request = _FakeRequest(app)

    await manager.note_stream_open(session.session_id, stream_id="stream-1")
    session.queue.put_nowait(json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"n": 1}}))
    session.queue.put_nowait(json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"n": 2}}))

    first_stream = _stream_session_events(
        request,
        session.session_id,
        session,
        "stream-1",
    )
    first_events = await _collect_events(first_stream, limit=2)
    await first_stream.aclose()

    assert 'id: stream-1:1' in first_events[1]
    assert '"n": 1' in first_events[1]

    session.queue.put_nowait(json.dumps({"jsonrpc": "2.0", "method": "notifications/progress", "params": {"n": 3}}))

    resume_stream = _stream_session_events(
        request,
        session.session_id,
        session,
        "stream-1",
        last_event_id="stream-1:1",
    )
    resumed_events = await _collect_events(resume_stream, limit=3)
    await resume_stream.aclose()

    assert 'id: stream-1:2' in resumed_events[1]
    assert '"n": 2' in resumed_events[1]
    assert 'id: stream-1:3' in resumed_events[2]
    assert '"n": 3' in resumed_events[2]
