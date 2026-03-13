import pytest

from pymcp import create_app


pytestmark = pytest.mark.anyio


@pytest.fixture
def app(sample_capabilities):
    return create_app(middleware_config=None)


class StreamableHttpClient:
    def __init__(self, session, app):
        self.session = session
        self.app = app
        self.session_id: str | None = None

    def _headers(self, *, accept: str = "application/json, text/event-stream") -> dict[str, str]:
        headers = {"Accept": accept}
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        return headers

    async def send_request(self, method: str, params: dict | None = None, request_id: int = 1):
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params:
            payload["params"] = params

        response = await self.session.post(
            "/mcp",
            json=payload,
            headers=self._headers(),
            timeout=5.0,
        )
        session_id = response.headers.get("MCP-Session-Id")
        if session_id:
            self.session_id = session_id
        return response

    async def send_notification(self, method: str, params: dict | None = None):
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params

        return await self.session.post(
            "/mcp",
            json=payload,
            headers=self._headers(),
            timeout=5.0,
        )

    async def initialize(
        self,
        *,
        protocol_version: str = "2025-06-18",
        request_id: int = 1,
        capabilities: dict | None = None,
    ) -> dict:
        params = {"protocolVersion": protocol_version}
        if capabilities:
            params["capabilities"] = capabilities
        response = await self.send_request("initialize", params=params, request_id=request_id)
        assert response.status_code == 200, response.text
        body = response.json()
        if "error" not in body:
            ready = await self.send_notification("notifications/initialized")
            assert ready.status_code == 202, ready.text
        return body


@pytest.fixture
async def client(api_client, app):
    yield StreamableHttpClient(api_client, app)


async def test_initialize_method(client):
    response = await client.initialize(request_id=1)

    assert client.session_id
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert "capabilities" in response["result"]


async def test_missing_session_header_returns_400(api_client):
    response = await api_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={"Accept": "application/json, text/event-stream"},
        timeout=5.0,
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "MCP-Session-Id header required"


async def test_methods_rejected_before_initialized_notification(client):
    response = await client.send_request(
        "initialize",
        params={"protocolVersion": "2025-06-18"},
        request_id=1,
    )
    assert response.status_code == 200

    blocked = await client.send_request("tools/list", request_id=2)
    body = blocked.json()
    assert body["error"]["code"] == -32600
    assert body["error"]["message"] == "server not initialized."


async def test_tools_list_method(client):
    await client.initialize(request_id=1)

    response = await client.send_request("tools/list", request_id=2)
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["tools"]
    assert any(tool["name"] == "add_numbers_tool" for tool in body["result"]["tools"])


async def test_tools_call_method(client):
    await client.initialize(request_id=1)

    response = await client.send_request(
        "tools/call",
        params={"name": "add_numbers_tool", "arguments": {"a": 5, "b": 3}},
        request_id=3,
    )
    body = response.json()
    assert body["result"]["content"][0]["text"] == "Sum of 5 + 3 = 8"


async def test_prompts_get_method(client):
    await client.initialize(request_id=1)

    response = await client.send_request(
        "prompts/get",
        params={"name": "summarize_prompt", "arguments": {"topic": "latency"}},
        request_id=4,
    )
    body = response.json()
    assert "latency" in body["result"]["messages"][0]["content"]["text"]


async def test_resources_read_method(client):
    await client.initialize(request_id=1)

    response = await client.send_request(
        "resources/read",
        params={"uri": "memo://release-plan"},
        request_id=5,
    )
    body = response.json()
    assert body["result"]["contents"][0]["mimeType"] == "text/markdown"


async def test_invalid_session_returns_404_jsonrpc_error(api_client):
    response = await api_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={
            "Accept": "application/json, text/event-stream",
            "MCP-Session-Id": "missing-session",
        },
        timeout=5.0,
    )

    assert response.status_code == 404
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["error"]["message"] == "Session not found"


async def test_stream_requires_session_header(api_client):
    response = await api_client.get(
        "/mcp",
        headers={"Accept": "text/event-stream"},
        timeout=5.0,
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "MCP-Session-Id header required"


async def test_delete_closes_session(client):
    await client.initialize(request_id=1)

    response = await client.session.delete(
        "/mcp",
        headers=client._headers(),
        timeout=5.0,
    )
    assert response.status_code == 204

    follow_up = await client.send_request("tools/list", request_id=2)
    assert follow_up.status_code == 404
    assert follow_up.json()["error"]["message"] == "Session not found"
