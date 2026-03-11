import asyncio
import json

import pytest

from pymcp import create_app
from pymcp.session.store import get_session_manager
from tests.support import register_sample_capabilities


pytestmark = pytest.mark.anyio("asyncio")


@pytest.fixture
def app():
    register_sample_capabilities()
    return create_app(middleware_config=None)


class HTTPCursorClient:
    def __init__(self, session, app):
        self.session = session
        self.app = app
        self.session_id: str | None = None
        self.stream_messages: list[dict | str] = []
        self.queue = None

    async def connect(self) -> str:
        manager = get_session_manager(self.app)
        session = manager.create_session()
        self.session_id = session.session_id
        self.queue = session.queue
        endpoint_url = f"http://testserver/message?sessionId={self.session_id}"
        self.stream_messages.append({"endpoint": endpoint_url})
        return self.session_id

    async def _drain_queue(self, timeout: float = 0.1) -> None:
        if self.queue is None:
            return
        while True:
            try:
                async with asyncio.timeout(timeout):
                    message = await self.queue.get()
            except asyncio.TimeoutError:
                break
            try:
                self.stream_messages.append(json.loads(message))
            except json.JSONDecodeError:
                self.stream_messages.append(message)

    async def send_request(self, method: str, params: dict | None = None, request_id: int = 1) -> dict:
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params:
            payload["params"] = params

        response = await self.session.post(
            f"/message?sessionId={self.session_id}",
            json=payload,
            timeout=5.0,
        )
        assert response.status_code == 200, response.text
        await self._drain_queue()
        return response.json()

    async def send_notification(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params

        response = await self.session.post(
            f"/message?sessionId={self.session_id}",
            json=payload,
            timeout=5.0,
        )
        assert response.status_code == 202, response.text
        await self._drain_queue()

    async def initialize(
        self,
        protocol_version: str = "2025-06-18",
        request_id: int = 1,
        capabilities: dict | None = None,
    ) -> dict:
        params = {"protocolVersion": protocol_version}
        if capabilities:
            params["capabilities"] = capabilities
        response = await self.send_request("initialize", params=params, request_id=request_id)
        if "error" not in response:
            await self.send_notification("notifications/initialized")
        return response

    async def wait_for_stream_message(self, timeout: float = 1.0) -> dict | None:
        await self._drain_queue(timeout=timeout)
        for message in reversed(self.stream_messages):
            if isinstance(message, dict) and message.get("jsonrpc") == "2.0":
                return message
        return None


@pytest.fixture
async def client(api_client, app):
    yield HTTPCursorClient(api_client, app)


async def test_connection_establishment(client):
    session_id = await client.connect()
    assert session_id
    assert client.stream_messages[0]["endpoint"].endswith(session_id)


async def test_initialize_method(client):
    await client.connect()
    response = await client.initialize(request_id=1)

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert "capabilities" in response["result"]

    stream_message = await client.wait_for_stream_message()
    assert stream_message is not None
    assert stream_message["id"] == 1


async def test_methods_rejected_before_initialize(client):
    await client.connect()
    response = await client.send_request("tools/list", request_id=999)
    assert response["error"]["code"] == -32600
    assert response["error"]["message"] == "server not initialized."


async def test_tools_list_method(client):
    await client.connect()
    await client.initialize(request_id=1)

    response = await client.send_request("tools/list", request_id=2)
    assert response["result"]["tools"]
    assert any(tool["name"] == "add_numbers_tool" for tool in response["result"]["tools"])


async def test_tools_call_method(client):
    await client.connect()
    await client.initialize(request_id=1)

    response = await client.send_request(
        "tools/call",
        params={"name": "add_numbers_tool", "arguments": {"a": 5, "b": 3}},
        request_id=3,
    )

    assert response["result"]["content"][0]["text"] == "Sum of 5 + 3 = 8"


async def test_prompts_get_method(client):
    await client.connect()
    await client.initialize(request_id=1)

    response = await client.send_request(
        "prompts/get",
        params={"name": "summarize_prompt", "arguments": {"topic": "latency"}},
        request_id=4,
    )

    assert "latency" in response["result"]["messages"][0]["content"]["text"]


async def test_resources_read_method(client):
    await client.connect()
    await client.initialize(request_id=1)

    response = await client.send_request(
        "resources/read",
        params={"uri": "memo://release-plan"},
        request_id=5,
    )

    assert response["result"]["contents"][0]["mimeType"] == "text/markdown"


async def test_invalid_session_returns_404(api_client):
    response = await api_client.post(
        "/message?sessionId=missing-session",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        timeout=5.0,
    )

    assert response.status_code == 404
    assert response.json()["error"] == "Invalid or missing sessionId"
