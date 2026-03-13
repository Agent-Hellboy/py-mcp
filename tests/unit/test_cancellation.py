import pytest

from pymcp import create_app
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session import get_session_manager
from pymcp.tasks.cancellation import CancellationToken, CancelledError, get_cancellation_manager


pytestmark = pytest.mark.anyio


async def test_cancel_notification_marks_request_cancelled():
    app = create_app(middleware_config=None)
    session_manager = get_session_manager(app)
    session = session_manager.create_session()
    await session_manager.mark_initialize_started(session.session_id)
    await session_manager.mark_initialized(session.session_id)

    result = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": "req-123", "reason": "stop"},
        },
        app=app,
        direct_response=True,
    )

    assert result.status == 202
    assert get_cancellation_manager(app).is_cancelled("req-123") is True


async def test_cancellation_token_raises_after_cancel():
    app = create_app(middleware_config=None)
    manager = get_cancellation_manager(app)
    token_value = manager.create_token("req-456")
    token = CancellationToken(token_value, manager)

    manager.cancel(token_value)

    with pytest.raises(CancelledError):
        token.check_cancelled()
