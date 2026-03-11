from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.session import get_session_store
from tests.support import register_sample_capabilities


def _build_client_and_session():
    app = create_app()
    session = get_session_store(app).create()
    return TestClient(app), session.session_id


def test_root():
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["transport"]["sse"] == "/sse-cursor"


def test_sse_route_is_registered():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/sse-cursor" in paths
    assert "/mcp/sse" in paths


def test_initialize_returns_capabilities():
    register_sample_capabilities()
    client, session_id = _build_client_and_session()
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    response = client.post(f"/message?sessionId={session_id}", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in body["result"]["capabilities"]
    assert "prompts" in body["result"]["capabilities"]
    assert "resources" in body["result"]["capabilities"]


def test_requests_rejected_before_initialize():
    client, session_id = _build_client_and_session()
    response = client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    assert response.status_code == 200
    assert response.json()["error"]["message"] == "server not initialized."


def test_tool_list_and_call():
    register_sample_capabilities()
    client, session_id = _build_client_and_session()
    client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    response = client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {"add_numbers_tool", "greet_tool", "prompt_echo_tool"} <= names

    response = client.post(
        f"/message?sessionId={session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "add_numbers_tool", "arguments": {"a": 2, "b": 3}},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["content"][0]["text"] == "Sum of 2 + 3 = 5"


def test_prompt_methods():
    register_sample_capabilities()
    client, session_id = _build_client_and_session()
    client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    response = client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
    )
    assert response.status_code == 200
    prompts = response.json()["result"]["prompts"]
    assert prompts[0]["name"] == "summarize_prompt"

    response = client.post(
        f"/message?sessionId={session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "prompts/get",
            "params": {"name": "summarize_prompt", "arguments": {"topic": "latency"}},
        },
    )
    assert response.status_code == 200
    message = response.json()["result"]["messages"][0]["content"]["text"]
    assert "latency" in message


def test_resource_methods():
    register_sample_capabilities()
    client, session_id = _build_client_and_session()
    client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    response = client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
    )
    assert response.status_code == 200
    resources = response.json()["result"]["resources"]
    assert resources[0]["uri"] == "memo://release-plan"

    response = client.post(
        f"/message?sessionId={session_id}",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": "memo://release-plan"},
        },
    )
    assert response.status_code == 200
    assert response.json()["result"]["contents"][0]["mimeType"] == "text/markdown"


def test_initialized_notification_is_accepted():
    client, session_id = _build_client_and_session()
    client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )

    response = client.post(
        f"/message?sessionId={session_id}",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
    )
    assert response.status_code == 202


def test_double_initialize_is_rejected():
    client, session_id = _build_client_and_session()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    first = client.post(f"/message?sessionId={session_id}", json=payload)
    second = client.post(f"/message?sessionId={session_id}", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["error"]["message"] == "server already initialized."
