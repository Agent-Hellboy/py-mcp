import pytest

from pymcp import create_app
from pymcp.registry import prompt_registry, tool_registry
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.settings import CapabilitySettings, ServerSettings


pytestmark = pytest.mark.anyio


async def _initialize_session(app):
    from pymcp.session.store import get_session_manager

    manager = get_session_manager(app)
    session = manager.create_session()
    await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
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
    return session


async def test_tools_list_pagination():
    for index in range(3):

        @tool_registry.register(name=f"tool_{index}")
        def sample_tool() -> str:
            return "ok"

    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(list_page_size=2),
        ),
    )
    session = await _initialize_session(app)

    first_page = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        app=app,
        direct_response=True,
    )
    assert len(first_page.payload["result"]["tools"]) == 2
    assert first_page.payload["result"]["nextCursor"] == "2"

    second_page = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/list",
            "params": {"cursor": "2"},
        },
        app=app,
        direct_response=True,
    )
    assert len(second_page.payload["result"]["tools"]) == 1
    assert "nextCursor" not in second_page.payload["result"]


async def test_tools_list_rejects_invalid_cursor():
    @tool_registry.register(name="single_tool")
    def single_tool() -> str:
        return "ok"

    app = create_app(middleware_config=None)
    session = await _initialize_session(app)

    response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {"cursor": "bad-cursor"},
        },
        app=app,
        direct_response=True,
    )
    assert response.payload["error"]["code"] == -32602


async def test_prompts_list_pagination():
    for index in range(3):

        @prompt_registry.register(name=f"prompt_{index}")
        def sample_prompt() -> str:
            return f"prompt {index}"

    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(list_page_size=2),
        ),
    )
    session = await _initialize_session(app)

    first_page = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
        app=app,
        direct_response=True,
    )
    assert len(first_page.payload["result"]["prompts"]) == 2
    assert first_page.payload["result"]["nextCursor"] == "2"

    second_page = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "prompts/list",
            "params": {"cursor": "2"},
        },
        app=app,
        direct_response=True,
    )
    assert len(second_page.payload["result"]["prompts"]) == 1
    assert "nextCursor" not in second_page.payload["result"]
