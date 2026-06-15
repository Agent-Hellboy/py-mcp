"""MCP server fixture exercised by the official conformance test suite."""

from __future__ import annotations

from pymcp import (
    CapabilitySettings,
    ServerSettings,
    create_app,
    prompt_registry,
    resource_registry,
    tool_registry,
)


@tool_registry.register(
    name="echo",
    title="Echo",
    output_schema={
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
    },
)
def echo(value: str) -> dict:
    """Return the supplied string."""

    return {
        "content": [{"type": "text", "text": value}],
        "structuredContent": {"value": value},
    }


@prompt_registry.register(name="greeting", description="Generate a greeting.")
def greeting(name: str) -> str:
    return f"Hello, {name}!"


@resource_registry.register(
    uri="test://static",
    name="static_resource",
    description="Static conformance resource.",
)
def static_resource() -> str:
    return "conformance"


@resource_registry.register_template(
    uri_template="test://items/{item}",
    name="item_resource",
    description="Parameterized conformance resource.",
)
def item_resource(item: str) -> str:
    return item


app = create_app(
    middleware_config=None,
    server_settings=ServerSettings(
        name="pymcp-kit-conformance",
        version="0.1.0",
        capabilities=CapabilitySettings(
            prompts_list_changed=True,
            resources_list_changed=True,
            resources_subscribe=True,
            tools_list_changed=True,
            logging_enabled=True,
            completions_enabled=True,
            tasks_enabled=True,
        ),
    ),
)
