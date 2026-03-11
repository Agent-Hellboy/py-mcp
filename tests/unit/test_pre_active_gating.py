import pytest

from pymcp import create_app
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.store import get_session_manager


pytestmark = pytest.mark.anyio("asyncio")


async def test_non_initialize_method_rejected_before_ready():
    app = create_app(middleware_config=None)
    session = get_session_manager(app).create_session()

    result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        app=app,
        direct_response=True,
    )

    assert result.status == 200
    assert result.payload["error"]["code"] == -32600
    assert result.payload["error"]["message"] == "server not initialized."


async def test_initialize_rejected_after_ready():
    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()
    manager.mark_initialized(session.session_id)

    result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {}},
        app=app,
        direct_response=True,
    )

    assert result.status == 200
    assert result.payload["error"]["code"] == -32600
    assert result.payload["error"]["message"] == "server already initialized."
