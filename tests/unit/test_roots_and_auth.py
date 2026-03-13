import pytest
from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.security import TokenMapAuthenticator
from pymcp.session.store import get_session_manager


pytestmark = pytest.mark.anyio


def test_initialize_requires_auth_when_configured():
    app = create_app(
        middleware_config=None,
        authn=TokenMapAuthenticator({"secret-token": {"subject": "alice"}}),
        require_authn=True,
    )
    client = TestClient(app)

    unauthorized = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == -32006

    authorized = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer secret-token",
        },
    )
    assert authorized.status_code == 200
    session_id = authorized.headers["MCP-Session-Id"]
    session = get_session_manager(app).get_session(session_id)
    assert session is not None
    assert session.principal is not None
    assert session.principal.subject == "alice"


async def test_roots_list_returns_configured_roots():
    app = create_app(
        middleware_config=None,
        roots=[{"uri": "file:///workspace", "name": "workspace"}],
    )
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

    response = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "roots/list"},
        app=app,
        direct_response=True,
    )
    assert response.payload["result"]["roots"] == [{"uri": "file:///workspace", "name": "workspace"}]
