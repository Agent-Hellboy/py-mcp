import asyncio
import json
import queue

import pytest

from pymcp import create_app
from pymcp.registry import tool_registry
from pymcp.session import get_session_manager
from pymcp.transport import StdioTransport
from tests.support import register_sample_capabilities


pytestmark = pytest.mark.anyio


class QueueInput:
    def __init__(self) -> None:
        self._lines: queue.Queue[str | None] = queue.Queue()

    def push(self, payload: dict[str, object]) -> None:
        self._lines.put(json.dumps(payload) + "\n")

    def close(self) -> None:
        self._lines.put(None)

    def readline(self) -> str:
        item = self._lines.get()
        if item is None:
            return ""
        return item


class QueueOutput:
    def __init__(self) -> None:
        self._lines: queue.Queue[str] = queue.Queue()
        self._buffer = ""

    def write(self, data: str) -> int:
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self._lines.put(line)
        return len(data)

    def flush(self) -> None:
        return None

    async def next_payload(self) -> dict[str, object]:
        line = await asyncio.to_thread(self._lines.get)
        return json.loads(line)


async def test_stdio_transport_round_trip():
    register_sample_capabilities()
    app = create_app(middleware_config=None)
    transport = StdioTransport()

    initialize = await transport.handle_line(
        app,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        ),
    )
    assert initialize is not None
    assert initialize["result"]["protocolVersion"] == "2025-06-18"

    ready = await transport.handle_line(
        app,
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    )
    assert ready is None

    listed = await transport.handle_line(
        app,
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    )
    assert listed is not None
    assert any(tool["name"] == "add_numbers_tool" for tool in listed["result"]["tools"])


async def test_stdio_transport_parse_error():
    app = create_app(middleware_config=None)
    transport = StdioTransport()

    response = await transport.handle_line(app, "{not-json}")
    assert response is not None
    assert response["error"]["code"] == -32700
    assert response["error"]["message"] == "Parse error"


async def test_stdio_transport_resolves_response_only_elicitation_message():
    app = create_app(middleware_config=None)
    transport = StdioTransport()

    await transport.handle_line(
        app,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        ),
    )
    session_id = transport._session_id
    assert session_id is not None

    manager = get_session_manager(app)
    future = asyncio.get_running_loop().create_future()
    manager.register_elicitation_future(
        session_id,
        "elic-stdio",
        future,
    )

    response = await transport.handle_line(
        app,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "elic-stdio",
                "result": {"action": "accept"},
            }
        ),
    )
    assert response is None
    assert future.result()["result"]["action"] == "accept"


async def test_stdio_transport_delivers_task_side_channel_messages_while_waiting_on_result():
    progress_allowed = asyncio.Event()
    finish_allowed = asyncio.Event()

    @tool_registry.register(name="stdio_task_progress_tool", execution={"taskSupport": "optional"})
    async def stdio_task_progress_tool(task_context) -> dict[str, object]:
        await progress_allowed.wait()
        await task_context.send_progress(1, total=2, message="halfway")
        await finish_allowed.wait()
        return {
            "content": [{"type": "text", "text": "done"}],
            "structuredContent": {"ok": True},
        }

    app = create_app(middleware_config=None)
    input_stream = QueueInput()
    output_stream = QueueOutput()
    transport = StdioTransport(input_stream=input_stream, output_stream=output_stream)
    runner = asyncio.create_task(transport.run(app))

    input_stream.push(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )
    initialize = await asyncio.wait_for(output_stream.next_payload(), timeout=1)
    assert initialize["result"]["protocolVersion"] == "2025-06-18"

    input_stream.push({"jsonrpc": "2.0", "method": "notifications/initialized"})

    input_stream.push(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "stdio_task_progress_tool",
                "arguments": {},
                "task": {"ttl": 1000},
            },
        }
    )
    call_response = await asyncio.wait_for(output_stream.next_payload(), timeout=1)
    task_id = call_response["result"]["task"]["taskId"]

    progress_allowed.set()
    input_stream.push(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tasks/result",
            "params": {"taskId": task_id},
        }
    )

    progress_notification = await asyncio.wait_for(output_stream.next_payload(), timeout=1)
    assert progress_notification["method"] == "notifications/progress"
    assert progress_notification["params"]["message"] == "halfway"

    finish_allowed.set()

    observed_methods: list[str] = []
    result_payload: dict[str, object] | None = None
    for _ in range(4):
        payload = await asyncio.wait_for(output_stream.next_payload(), timeout=1)
        method = payload.get("method")
        if isinstance(method, str):
            observed_methods.append(method)
        if payload.get("id") == 3:
            result_payload = payload
            break

    assert "notifications/tasks/status" in observed_methods
    assert result_payload is not None
    assert result_payload["result"]["structuredContent"] == {"ok": True}

    input_stream.close()
    await asyncio.wait_for(runner, timeout=1)
