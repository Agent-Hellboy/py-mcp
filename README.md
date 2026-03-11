# py-mcp

`py-mcp` is a capability-first MCP server toolkit for FastAPI. It keeps the transport layer small, supports Streamable HTTP and stdio only, and follows a layered structure inspired by the internal framework: app-scoped registries, a session manager, and a runtime dispatcher with method handlers.

## Quickstart

```bash
pip install .
python example/run_server.py
```

Transport entrypoints:

- Streamable HTTP at `/mcp`
- Stdio via `pymcp.transport.run_stdio_server(app)`

## Register capabilities

```python
from pymcp import (
    CapabilitySettings,
    ServerSettings,
    create_app,
    prompt_registry,
    resource_registry,
    tool_registry,
)


@tool_registry.register
def add(a: float, b: float) -> str:
    return f"{a + b}"


@prompt_registry.register(description="Create a release summary prompt.")
def summarize_release(topic: str) -> str:
    return f"Summarize the release impact for {topic}."


@resource_registry.register(
    uri="memo://release-plan",
    name="release_plan",
    description="Latest release checklist",
    mime_type="text/markdown",
)
def release_plan() -> str:
    return "# Release Plan\n- freeze API\n- tag build\n"


app = create_app(
    server_settings=ServerSettings(
        name="demo-server",
        version="0.2.0",
        capabilities=CapabilitySettings(
            advertise_empty_prompts=False,
            advertise_empty_resources=False,
        ),
    )
)
```

## What this repo implements

- `initialize`, `ping`
- `tools/list`, `tools/call`
- `prompts/list`, `prompts/get`
- `resources/list`, `resources/read`
- Configurable FastAPI middleware

The package intentionally stays smaller than a full multi-transport MCP framework. It focuses on the surfaces most teams need to stand up a usable server quickly.

## Stdio transport

```python
from pymcp import create_app, run_stdio_server


app = create_app()
run_stdio_server(app)
```

## Package shape

- `registries/`: tool, prompt, and resource registries plus `RegistryManager`
- `session/`: session types and `SessionManager`
- `runtime/dispatch.py`: JSON-RPC validation, gating, and handler routing
- `runtime/handlers/`: lifecycle, prompt, resource, and tool handlers
- `runtime/server.py`: FastAPI app factory
- `transport/streamable_http.py`: Streamable HTTP transport routes
- `transport/stdio.py`: stdio transport runner
- `server.py`: root route plus mounted HTTP transport

## Middleware

Middleware is configured separately from capability registration through `MiddlewareConfig`. See [guide.md](./guide.md).

## Notes

- The transport focus is Streamable HTTP and stdio.
- Registries are copied into an app-scoped manager when `create_app()` runs.
- Prompts and resources are advertised only when registered by default.
- Tasks, auth, and richer transport variants are intentionally out of scope for this package.
