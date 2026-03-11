import pytest

from pymcp.session.store import SessionManager


pytestmark = pytest.mark.anyio("asyncio")


async def test_stream_attachment_flags_toggle_without_lifecycle_change():
    manager = SessionManager()
    session = manager.create_session()
    session_id = session.session_id

    assert session.stream_attached is False

    await manager.note_stream_open(session_id, stream_id="s1", last_event_id="e1")
    assert session.stream_attached is True
    assert session.attached_stream_id == "s1"
    assert session.last_acked_event_id == "e1"
    lifecycle_state = session.lifecycle_state

    manager.mark_stream_detached(session_id, stream_id="s1")
    assert session.stream_attached is False
    assert session.lifecycle_state == lifecycle_state
