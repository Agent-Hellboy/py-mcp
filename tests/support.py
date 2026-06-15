from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.registry import prompt_registry, resource_registry, tool_registry
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.store import get_session_manager


def jsonrpc_headers(
    session_id: str | None = None,
    *,
    accept: str = "application/json, text/event-stream",
) -> dict[str, str]:
    headers = {"Accept": accept}
    if session_id:
        headers["MCP-Session-Id"] = session_id
    return headers


def register_sample_capabilities() -> None:
    @tool_registry.register
    def add_numbers_tool(a: float, b: float) -> str:
        """Adds two numbers."""
        return f"Sum of {a} + {b} = {a + b}"

    @tool_registry.register
    async def greet_tool(name: str) -> str:
        """Greets a user."""
        return f"Hello, {name}!"

    @tool_registry.register
    def prompt_echo_tool(prompt: str) -> str:
        """Echoes the provided prompt."""
        return f"You said: {prompt}"

    @prompt_registry.register(description="Summarize a support question for triage.")
    def summarize_prompt(topic: str) -> str:
        return f"Summarize the support issue about {topic} in three bullets."

    @resource_registry.register(
        uri="memo://release-plan",
        name="release_plan",
        description="Release checklist snapshot.",
        mime_type="text/markdown",
    )
    def release_plan() -> str:
        return "# Release Plan\n- add prompts\n- add resources\n"


def initialize_http_session(
    client: TestClient,
    *,
    protocol_version: str = "2025-11-25",
    request_id: int = 1,
) -> tuple[str, dict[str, object]]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    response = client.post("/mcp", json=payload, headers=jsonrpc_headers())
    assert response.status_code == 200
    return response.headers["MCP-Session-Id"], response.json()


async def initialize_ready_session(
    app=None,
    *,
    protocol_version: str = "2025-11-25",
):
    if app is None:
        app = create_app(middleware_config=None)

    manager = get_session_manager(app)
    session = manager.create_session()
    await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": protocol_version},
        },
        app=app,
        direct_response=True,
    )
    await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        app=app,
        direct_response=True,
    )
    return session
