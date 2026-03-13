import json

import pytest

from pymcp import create_app
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.store import get_session_manager


pytestmark = pytest.mark.anyio


async def test_dispatch_enqueues_response_for_session_stream(sample_capabilities):
    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()

    init_result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        app=app,
        direct_response=False,
    )
    queued_init = json.loads(await session.queue.get())
    assert queued_init == init_result.payload

    ready_result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        app=app,
        direct_response=False,
    )
    assert ready_result.payload is None

    list_result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        app=app,
        direct_response=False,
    )
    queued_list = json.loads(await session.queue.get())
    assert queued_list == list_result.payload
