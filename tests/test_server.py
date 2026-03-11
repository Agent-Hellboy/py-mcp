from fastapi.testclient import TestClient

from pymcp import create_app
from tests.support import register_sample_capabilities


def _headers(session_id=None, *, accept="application/json, text/event-stream"):
    headers = {"Accept": accept}
    if session_id:
        headers["MCP-Session-Id"] = session_id
    return headers


def _build_client(app=None):
    return TestClient(app if app is not None else create_app())


def _initialize_session(client: TestClient, *, protocol_version: str = "2025-06-18"):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    response = client.post("/mcp", json=payload, headers=_headers())
    assert response.status_code == 200
    return response.headers["MCP-Session-Id"], response


def test_root():
    client = _build_client()
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["transport"]["streamableHttp"] == "/mcp"
    assert payload["transport"]["stdio"] is True


def test_streamable_http_route_is_registered():
    app = create_app()
    paths = {route.path for route in app.routes}
    assert "/mcp" in paths
    assert "/sse-cursor" not in paths
    assert "/message" not in paths


def test_initialize_returns_capabilities():
    register_sample_capabilities()
    client = _build_client()
    session_id, response = _initialize_session(client)
    body = response.json()
    assert session_id
    assert body["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in body["result"]["capabilities"]
    assert "prompts" in body["result"]["capabilities"]
    assert "resources" in body["result"]["capabilities"]


def test_requests_without_session_header_are_rejected():
    client = _build_client()
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers=_headers(),
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "MCP-Session-Id header required"


def test_tool_list_and_call():
    register_sample_capabilities()
    client = _build_client()
    session_id, _ = _initialize_session(client)
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(session_id),
    )

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {"add_numbers_tool", "greet_tool", "prompt_echo_tool"} <= names

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "add_numbers_tool", "arguments": {"a": 2, "b": 3}},
        },
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    assert response.json()["result"]["content"][0]["text"] == "Sum of 2 + 3 = 5"


def test_prompt_methods():
    register_sample_capabilities()
    client = _build_client()
    session_id, _ = _initialize_session(client)
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(session_id),
    )

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    prompts = response.json()["result"]["prompts"]
    assert prompts[0]["name"] == "summarize_prompt"

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "prompts/get",
            "params": {"name": "summarize_prompt", "arguments": {"topic": "latency"}},
        },
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    message = response.json()["result"]["messages"][0]["content"]["text"]
    assert "latency" in message


def test_resource_methods():
    register_sample_capabilities()
    client = _build_client()
    session_id, _ = _initialize_session(client)
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(session_id),
    )

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    resources = response.json()["result"]["resources"]
    assert resources[0]["uri"] == "memo://release-plan"

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": "memo://release-plan"},
        },
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    assert response.json()["result"]["contents"][0]["mimeType"] == "text/markdown"


def test_initialized_notification_is_accepted():
    client = _build_client()
    session_id, _ = _initialize_session(client)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(session_id),
    )
    assert response.status_code == 202


def test_methods_remain_blocked_until_initialized_notification():
    register_sample_capabilities()
    client = _build_client()
    session_id, _ = _initialize_session(client)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    assert response.json()["error"]["message"] == "server not initialized."


def test_double_initialize_is_rejected():
    client = _build_client()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    first = client.post("/mcp", json=payload, headers=_headers())
    session_id = first.headers["MCP-Session-Id"]
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(session_id),
    )
    second = client.post("/mcp", json=payload, headers=_headers(session_id))
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["error"]["message"] == "server already initialized."


def test_stream_requires_session_header():
    client = _build_client()
    response = client.get("/mcp", headers=_headers(accept="text/event-stream"))
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "MCP-Session-Id header required"


def test_delete_closes_session():
    client = _build_client()
    session_id, _ = _initialize_session(client)

    response = client.delete("/mcp", headers=_headers(session_id))
    assert response.status_code == 204

    follow_up = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers=_headers(session_id),
    )
    assert follow_up.status_code == 404
    assert follow_up.json()["error"]["message"] == "Session not found"
