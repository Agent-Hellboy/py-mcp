from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.settings import ServerSettings
from tests.support import initialize_http_session, jsonrpc_headers


def _build_client(app=None):
    return TestClient(app if app is not None else create_app())


def _initialize_session(client: TestClient, *, protocol_version: str = "2025-06-18"):
    return initialize_http_session(client, protocol_version=protocol_version)


def _send_initialized(client: TestClient, session_id: str):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=jsonrpc_headers(session_id),
    )
    assert response.status_code == 202


def test_root():
    client = _build_client()
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["transport"]["streamableHttp"] == "/mcp"
    assert payload["transport"]["stdio"] is True


def test_default_server_settings_flow_into_initialize_and_root():
    client = _build_client()
    response = client.get("/")
    assert response.status_code == 200
    root_payload = response.json()
    assert root_payload["server"]["name"] == "pymcp-kit"
    assert root_payload["server"]["version"] == "0.1.0"

    _, body = _initialize_session(client)
    assert body["result"]["serverInfo"]["name"] == "pymcp-kit"
    assert body["result"]["serverInfo"]["version"] == "0.1.0"


def test_custom_server_settings_include_optional_metadata():
    client = _build_client(
        create_app(
            server_settings=ServerSettings(
                name="custom-server",
                version="1.2.3",
                title="Custom Server",
                description="Custom description",
                website_url="https://example.com",
                icons=[{"src": "https://example.com/icon.svg", "theme": "dark"}],
            )
        )
    )

    root_payload = client.get("/").json()
    assert root_payload["server"]["title"] == "Custom Server"
    assert root_payload["server"]["description"] == "Custom description"
    assert root_payload["server"]["websiteUrl"] == "https://example.com"
    assert root_payload["server"]["icons"][0]["theme"] == "dark"

    _, initialize_response = _initialize_session(client)
    server_info = initialize_response["result"]["serverInfo"]
    assert server_info["title"] == "Custom Server"
    assert server_info["description"] == "Custom description"
    assert server_info["websiteUrl"] == "https://example.com"
    assert server_info["icons"][0]["theme"] == "dark"


def test_streamable_http_route_is_registered():
    client = TestClient(create_app())
    assert client.post("/mcp", json={}).status_code != 404
    assert client.post("/message", json={}).status_code == 404


def test_initialize_returns_capabilities(sample_capabilities):
    client = _build_client()
    session_id, body = _initialize_session(client)
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
        headers=jsonrpc_headers(),
    )
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "MCP-Session-Id header required"


def test_tool_list_and_call(sample_capabilities):
    client = _build_client()
    session_id, _ = _initialize_session(client)
    _send_initialized(client, session_id)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers=jsonrpc_headers(session_id),
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
        headers=jsonrpc_headers(session_id),
    )
    assert response.status_code == 200
    assert response.json()["result"]["content"][0]["text"] == "Sum of 2 + 3 = 5"


def test_prompt_methods(sample_capabilities):
    client = _build_client()
    session_id, _ = _initialize_session(client)
    _send_initialized(client, session_id)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
        headers=jsonrpc_headers(session_id),
    )
    assert response.status_code == 200
    prompts = response.json()["result"]["prompts"]
    assert any(p["name"] == "summarize_prompt" for p in prompts)

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "prompts/get",
            "params": {"name": "summarize_prompt", "arguments": {"topic": "latency"}},
        },
        headers=jsonrpc_headers(session_id),
    )
    assert response.status_code == 200
    message = response.json()["result"]["messages"][0]["content"]["text"]
    assert "latency" in message


def test_resource_methods(sample_capabilities):
    client = _build_client()
    session_id, _ = _initialize_session(client)
    _send_initialized(client, session_id)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
        headers=jsonrpc_headers(session_id),
    )
    assert response.status_code == 200
    resources = response.json()["result"]["resources"]
    assert any(r["uri"] == "memo://release-plan" for r in resources)

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": "memo://release-plan"},
        },
        headers=jsonrpc_headers(session_id),
    )
    assert response.status_code == 200
    assert response.json()["result"]["contents"][0]["mimeType"] == "text/markdown"


def test_initialized_notification_is_accepted():
    client = _build_client()
    session_id, _ = _initialize_session(client)
    _send_initialized(client, session_id)


def test_methods_remain_blocked_until_initialized_notification(sample_capabilities):
    client = _build_client()
    session_id, _ = _initialize_session(client)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers=jsonrpc_headers(session_id),
    )
    assert response.status_code == 200
    assert response.json()["error"]["message"] == "server not initialized."


def test_double_initialize_is_rejected():
    client = _build_client()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    first = client.post("/mcp", json=payload, headers=jsonrpc_headers())
    session_id = first.headers["MCP-Session-Id"]
    _send_initialized(client, session_id)
    second = client.post("/mcp", json=payload, headers=jsonrpc_headers(session_id))
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["error"]["message"] == "server already initialized."


def test_stream_requires_session_header():
    client = _build_client()
    response = client.get("/mcp", headers=jsonrpc_headers(accept="text/event-stream"))
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "MCP-Session-Id header required"


def test_delete_closes_session():
    client = _build_client()
    session_id, _ = _initialize_session(client)
    _send_initialized(client, session_id)

    response = client.delete("/mcp", headers=jsonrpc_headers(session_id))
    assert response.status_code == 204

    follow_up = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        headers=jsonrpc_headers(session_id),
    )
    assert follow_up.status_code == 404
    assert follow_up.json()["error"]["message"] == "Session not found"
