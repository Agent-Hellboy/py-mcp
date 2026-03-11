import pytest

from pymcp import create_app
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.store import get_session_manager
from tests.support import register_sample_capabilities


pytestmark = pytest.mark.anyio("asyncio")


async def test_prompts_not_supported_when_registry_is_empty():
    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()
    manager.mark_initialized(session.session_id)

    result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 1, "method": "prompts/list"},
        app=app,
        direct_response=True,
    )

    assert result.status == 200
    assert result.payload["error"]["code"] == -32601
    assert result.payload["error"]["message"] == "prompts not supported"


async def test_resources_supported_once_registered():
    register_sample_capabilities()
    app = create_app(middleware_config=None)
    manager = get_session_manager(app)
    session = manager.create_session()
    manager.mark_initialized(session.session_id)

    result = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
        app=app,
        direct_response=True,
    )

    assert result.status == 200
    assert result.payload["result"]["resources"][0]["uri"] == "memo://release-plan"
