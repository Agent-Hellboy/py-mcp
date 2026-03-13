import asyncio

import pytest

from pymcp import create_app
from pymcp.registry import tool_registry
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.security.authn import Principal
from pymcp.session.store import get_session_manager
from pymcp.settings import CapabilitySettings, ServerSettings


pytestmark = pytest.mark.anyio


async def _initialize_ready(app, session_id: str):
    initialize = await process_jsonrpc_message(
        session_id,
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
        session_id,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        app=app,
        direct_response=True,
    )
    return initialize


async def test_task_augmented_tool_call_exposes_tasks_surface():
    @tool_registry.register(name="background_add", execution={"taskSupport": "optional"})
    async def background_add(a: int, b: int) -> str:
        await asyncio.sleep(0)
        return str(a + b)

    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()

    initialize = await _initialize_ready(app, session.session_id)
    assert initialize.payload["result"]["capabilities"]["tasks"]

    call_response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "background_add",
                "arguments": {"a": 2, "b": 3},
                "task": {"ttl": 1000},
            },
        },
        app=app,
        direct_response=True,
    )
    task = call_response.payload["result"]["task"]
    assert task["status"] == "working"
    task_id = task["taskId"]

    get_response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tasks/get",
            "params": {"taskId": task_id},
        },
        app=app,
        direct_response=True,
    )
    assert get_response.payload["result"]["taskId"] == task_id

    result_response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tasks/result",
            "params": {"taskId": task_id},
        },
        app=app,
        direct_response=True,
    )
    assert result_response.payload["_meta"]["io.modelcontextprotocol/related-task"]["taskId"] == task_id
    assert result_response.payload["result"]["content"][0]["text"] == "5"


async def test_task_metadata_is_ignored_when_tools_call_task_capability_is_not_advertised():
    @tool_registry.register(name="sync_add_without_task_capability", execution={"taskSupport": "optional"})
    def sync_add(a: int, b: int) -> str:
        return str(a + b)

    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(
                tasks_enabled=True,
                tasks_tool_call=False,
            )
        ),
    )
    manager = get_session_manager(app)
    session = manager.create_session()

    initialize = await _initialize_ready(app, session.session_id)
    tasks_caps = initialize.payload["result"]["capabilities"]["tasks"]
    assert "requests" not in tasks_caps

    response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "sync_add_without_task_capability",
                "arguments": {"a": 2, "b": 3},
                "task": {"ttl": 1000},
            },
        },
        app=app,
        direct_response=True,
    )

    assert "task" not in response.payload["result"]
    assert response.payload["result"]["content"][0]["text"] == "5"


async def test_tasks_bind_to_authorization_context_instead_of_session_id():
    @tool_registry.register(name="auth_bound_task_tool", execution={"taskSupport": "optional"})
    async def auth_bound_task_tool() -> dict[str, object]:
        await asyncio.sleep(0)
        return {
            "content": [{"type": "text", "text": "secured"}],
            "structuredContent": {"ok": True},
        }

    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    alice_one = manager.create_session()
    alice_two = manager.create_session()
    bob = manager.create_session()

    shared_claims = {"tenant": "acme"}
    alice_one.principal = Principal(
        subject="alice",
        scopes={"tasks:read"},
        roles={"operator"},
        claims=shared_claims,
    )
    alice_two.principal = Principal(
        subject="alice",
        scopes={"tasks:read"},
        roles={"operator"},
        claims=shared_claims,
    )
    bob.principal = Principal(
        subject="bob",
        scopes={"tasks:read"},
        roles={"operator"},
        claims=shared_claims,
    )

    await _initialize_ready(app, alice_one.session_id)
    await _initialize_ready(app, alice_two.session_id)
    await _initialize_ready(app, bob.session_id)

    create_response = await process_jsonrpc_message(
        alice_one.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "auth_bound_task_tool",
                "arguments": {},
                "task": {"ttl": 1000},
            },
        },
        app=app,
        direct_response=True,
    )
    task_id = create_response.payload["result"]["task"]["taskId"]

    same_principal_get = await process_jsonrpc_message(
        alice_two.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tasks/get",
            "params": {"taskId": task_id},
        },
        app=app,
        direct_response=True,
    )
    assert same_principal_get.payload["result"]["taskId"] == task_id

    same_principal_list = await process_jsonrpc_message(
        alice_two.session_id,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tasks/list",
            "params": {},
        },
        app=app,
        direct_response=True,
    )
    assert {task["taskId"] for task in same_principal_list.payload["result"]["tasks"]} == {task_id}

    other_principal_get = await process_jsonrpc_message(
        bob.session_id,
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tasks/get",
            "params": {"taskId": task_id},
        },
        app=app,
        direct_response=True,
    )
    assert other_principal_get.payload["error"]["code"] == -32602

    other_principal_list = await process_jsonrpc_message(
        bob.session_id,
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tasks/list",
            "params": {},
        },
        app=app,
        direct_response=True,
    )
    assert other_principal_list.payload["result"]["tasks"] == []

    same_principal_result = await process_jsonrpc_message(
        alice_two.session_id,
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tasks/result",
            "params": {"taskId": task_id},
        },
        app=app,
        direct_response=True,
    )
    assert same_principal_result.payload["result"]["structuredContent"] == {"ok": True}


async def test_tool_results_preserve_rich_payloads_for_direct_and_task_calls():
    @tool_registry.register(name="rich_payload_tool", execution={"taskSupport": "optional"})
    def rich_payload_tool() -> dict[str, object]:
        return {
            "content": [{"type": "text", "text": "done"}],
            "structuredContent": {"ok": True, "items": [1, 2, 3]},
            "isError": False,
        }

    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()
    await _initialize_ready(app, session.session_id)

    direct_response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "rich_payload_tool", "arguments": {}},
        },
        app=app,
        direct_response=True,
    )
    assert direct_response.payload["result"]["structuredContent"] == {"ok": True, "items": [1, 2, 3]}

    task_response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "rich_payload_tool",
                "arguments": {},
                "task": {"ttl": 1000},
            },
        },
        app=app,
        direct_response=True,
    )
    task_id = task_response.payload["result"]["task"]["taskId"]

    result_response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tasks/result",
            "params": {"taskId": task_id},
        },
        app=app,
        direct_response=True,
    )
    assert result_response.payload["result"]["content"][0]["text"] == "done"
    assert result_response.payload["result"]["structuredContent"] == {"ok": True, "items": [1, 2, 3]}
