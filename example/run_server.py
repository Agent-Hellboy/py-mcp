"""Example MCP server with notification support for client testing (e.g. Cursor).

Run for HTTP:
    python run_server.py

Run for Cursor (stdio MCP):
    python run_server.py --stdio

Cursor ``mcp.json`` example:
    {
      "mcpServers": {
        "py-mcp-example": {
          "command": "/path/to/.venv/bin/python",
          "args": ["/path/to/py-mcp/example/run_server.py", "--stdio"]
        }
      }
    }

After connecting the client:
- Call ``registerBonusTool`` to emit ``notifications/tools/list_changed``
- Call ``sendLogNotificationTool`` to emit ``notifications/message``
- Subscribe to ``memo://welcome``, then call ``refreshWelcomeMemo`` for
  ``notifications/resources/updated``
"""

import logging

from config import middleware_config
from pymcp import (
    CapabilitySettings,
    ServerSettings,
    create_app,
    prompt_registry,
    resource_registry,
    tool_registry,
)
from pymcp.registries.registry import get_registry_manager
from pymcp.runtime.context import RequestContext
from pymcp.session.notifications import send_log_message

logging.basicConfig(level=logging.DEBUG)


@tool_registry.register
def addNumbersTool(a: float, b: float) -> str:
    """Adds two numbers 'a' and 'b' and returns their sum."""
    return f"Sum of {a} + {b} = {a + b}"


@tool_registry.register
def multiplyNumbersTool(a: float, b: float) -> str:
    """Multiplies two numbers 'a' and 'b' and returns their product."""
    return f"Product of {a} * {b} = {a * b}"


@tool_registry.register
def greetTool(name: str) -> str:
    """Greets a person by their name."""
    return f"Hello, {name}! Nice to meet you!"


@tool_registry.register
def calculateAreaTool(length: float, width: float) -> str:
    """Calculates the area of a rectangle given length and width."""
    area = length * width
    return f"Area of rectangle with length {length} and width {width} = {area}"


@tool_registry.register
def promptEchoTool(prompt: str) -> str:
    """Echoes back the prompt provided, with input validation."""
    if not prompt or "crash" in prompt.lower():
        return "Invalid input. Please try again."
    return f"You said: {prompt}"


@tool_registry.register
def registerBonusTool(request_context: RequestContext) -> str:
    """Register bonusTool at runtime and notify clients that the tools list changed."""

    registry = get_registry_manager(request_context.app).get_tool_registry()

    @registry.register(name="bonusTool")
    def bonusTool(n: int) -> str:
        """Adds 100 to n."""
        return str(n + 100)

    return "Registered bonusTool. Connected clients should receive notifications/tools/list_changed."


@tool_registry.register
async def sendLogNotificationTool(message: str, request_context: RequestContext) -> str:
    """Send a structured log notification (notifications/message) to the connected client."""

    session_id = request_context.session_id
    if not session_id:
        return "No session id available for this call."

    sent = await send_log_message(
        request_context.app,
        session_id,
        level="info",
        logger="example-server",
        data={"message": message},
    )
    if sent:
        return f"Sent notifications/message: {message}"
    return (
        "Log notification was not delivered. Ensure logging is enabled, "
        "the client completed initialize, and the SSE stream is open."
    )


@tool_registry.register
def refreshWelcomeMemo(request_context: RequestContext) -> str:
    """Notify subscribed clients that memo://welcome was updated."""

    get_registry_manager(request_context.app).get_resource_registry().notify_updated("memo://welcome")
    return "Sent notifications/resources/updated for memo://welcome (subscribed clients only)."


@prompt_registry.register(description="Prompt template for release notes.")
def releaseNotesPrompt(service: str) -> str:
    return f"Draft a short release note for the {service} service."


@resource_registry.register(
    uri="memo://welcome",
    name="welcome_memo",
    description="Plain text welcome memo for clients.",
)
def welcomeMemo() -> str:
    return "Welcome to PyMCP Kit. Use tools for actions and resources for read-only context."


@resource_registry.register_template(
    uri_template="note://{topic}",
    name="topic_note",
    description="Parameterized note resource keyed by topic.",
)
def topicNote(topic: str) -> str:
    return f"Notes for topic: {topic}"


if __name__ == "__main__":
    import sys

    from pymcp import run_http_server, run_stdio_server

    app = create_app(
        middleware_config=middleware_config,
        server_settings=ServerSettings(
            name="example-server",
            version="0.1.0",
            capabilities=CapabilitySettings(
                advertise_empty_prompts=False,
                advertise_empty_resources=False,
                tools_list_changed=True,
                prompts_list_changed=True,
                resources_list_changed=True,
                logging_enabled=True,
            ),
        ),
    )

    if "--stdio" in sys.argv:
        run_stdio_server(app)
    else:
        run_http_server(app, host="0.0.0.0", port=8088)
