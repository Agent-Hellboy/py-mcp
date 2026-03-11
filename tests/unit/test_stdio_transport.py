import json

import pytest

from pymcp import create_app
from pymcp.transport import StdioTransport
from tests.support import register_sample_capabilities


pytestmark = pytest.mark.anyio("asyncio")


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
