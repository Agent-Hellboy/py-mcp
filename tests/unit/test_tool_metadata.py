"""Tests for extended tool declaration and result metadata."""

import pytest

from pymcp import create_app
from pymcp.protocol.types import (
    Annotations,
    AudioContent,
    EmbeddedResource,
    ImageContent,
    ResourceLink,
    TextResourceContents,
    Tool,
    ToolAnnotations,
    ToolIcon,
)
from pymcp.registry import tool_registry
from pymcp.runtime.dispatch import process_jsonrpc_message


pytestmark = pytest.mark.anyio


async def _initialize(app, session_id: str) -> None:
    await process_jsonrpc_message(
        session_id,
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
        session_id,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        app=app,
        direct_response=True,
    )


async def test_tools_list_includes_extended_metadata():
    @tool_registry.register(
        title="Add numbers",
        output_schema={
            "type": "object",
            "properties": {"sum": {"type": "number"}},
            "required": ["sum"],
        },
        annotations={
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        },
        icons=[{"src": "https://example.com/add.svg", "mimeType": "image/svg+xml"}],
    )
    def metadataDemoTool(a: float, b: float) -> dict[str, object]:
        """Adds two numbers."""
        total = a + b
        return {
            "content": [{"type": "text", "text": str(total)}],
            "structuredContent": {"sum": total},
        }

    app = create_app(middleware_config=None)
    session = app.state.session_manager.create_session()
    await _initialize(app, session.session_id)

    response = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        app=app,
        direct_response=True,
    )
    tools = response.payload["result"]["tools"]
    tool = next(item for item in tools if item["name"] == "metadataDemoTool")

    assert tool["title"] == "Add numbers"
    assert tool["outputSchema"]["properties"]["sum"]["type"] == "number"
    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["icons"][0]["src"] == "https://example.com/add.svg"

    validated = Tool.model_validate(tool)
    assert validated.title == "Add numbers"
    assert validated.outputSchema is not None
    assert validated.annotations == ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        openWorldHint=False,
        idempotentHint=True,
    )
    assert validated.icons == [
        ToolIcon(src="https://example.com/add.svg", mimeType="image/svg+xml"),
    ]


async def test_tools_call_returns_structured_content():
    @tool_registry.register(
        output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
    )
    def structuredResultTool(value: str) -> dict[str, object]:
        return {
            "structuredContent": {"value": value},
            "content": [{"type": "text", "text": value}],
        }

    app = create_app(middleware_config=None)
    session = app.state.session_manager.create_session()
    await _initialize(app, session.session_id)

    response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "structuredResultTool", "arguments": {"value": "hello"}},
        },
        app=app,
        direct_response=True,
    )

    result = response.payload["result"]
    assert result["structuredContent"] == {"value": "hello"}
    assert result["content"][0]["text"] == "hello"


def test_tool_definition_omits_empty_optional_fields():
    @tool_registry.register
    def plainTool() -> str:
        return "ok"

    payload = tool_registry.get("plainTool").to_mcp_payload()
    assert set(payload.keys()) == {"name", "description", "inputSchema"}


def test_shared_protocol_models_support_extended_metadata():
    icon = ToolIcon(src="https://example.com/icon.svg", theme="dark")
    assert icon.model_dump(exclude_none=True)["theme"] == "dark"

    image = ImageContent(
        data="aGVsbG8=",
        mimeType="image/png",
        annotations=Annotations(priority=0.5),
    )
    audio = AudioContent(
        data="aGVsbG8=",
        mimeType="audio/wav",
        annotations=Annotations(audience=["user"]),
    )
    resource_link = ResourceLink(
        uri="test://link",
        name="Link",
        title="Linked Resource",
        mimeType="text/plain",
        size=12,
    )
    embedded = EmbeddedResource(
        resource=TextResourceContents(uri="test://embedded", mimeType="text/plain", text="payload"),
        annotations=Annotations(lastModified="2025-01-01T00:00:00Z"),
    )

    assert image.annotations is not None and image.annotations.priority == 0.5
    assert audio.annotations is not None and audio.annotations.audience == ["user"]
    assert resource_link.type == "resource_link"
    assert resource_link.title == "Linked Resource"
    assert embedded.annotations is not None and embedded.annotations.lastModified
