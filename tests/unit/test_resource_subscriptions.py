import json

import pytest

from pymcp import create_app
from pymcp.registry import resource_registry
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.store import get_session_manager


pytestmark = pytest.mark.anyio


async def test_resource_subscriptions_emit_update_notifications():
    @resource_registry.register(
        uri="memo://subscription-test",
        name="subscription_test",
        description="A resource used to test subscriptions.",
        mime_type="text/plain",
    )
    def subscription_test_resource() -> str:
        return "hello"

    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()

    await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        app=app,
        direct_response=True,
    )
    await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        app=app,
        direct_response=True,
    )
    await manager.note_stream_open(session.session_id, stream_id="stream-1")

    subscribe = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/subscribe",
            "params": {"uri": "memo://subscription-test"},
        },
        app=app,
        direct_response=True,
    )
    assert subscribe.payload["result"]["subscribed"] == ["memo://subscription-test"]

    app.state.registry_manager.resource_registry.notify_updated("memo://subscription-test")
    message = json.loads(await session.queue.get())
    assert message["method"] == "notifications/resources/updated"
    assert message["params"]["uri"] == "memo://subscription-test"

    unsubscribe = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/unsubscribe",
            "params": {"uri": "memo://subscription-test"},
        },
        app=app,
        direct_response=True,
    )
    assert unsubscribe.payload["result"]["unsubscribed"] == ["memo://subscription-test"]
