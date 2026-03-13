# Getting Started

This guide covers the public surface that ships in `pymcp-kit` today.

## Installation

Install the package from PyPI:

```bash
pip install pymcp-kit
```

For local development from this repository:

```bash
pip install -e .
```

If you want to work on the docs locally as well:

```bash
pip install -e '.[docs]'
```

## Quick Start

Register tools, prompts, and resources before calling `create_app()`:

```python
from pymcp import (
    CapabilitySettings,
    ServerSettings,
    create_app,
    prompt_registry,
    resource_registry,
    tool_registry,
)


@tool_registry.register(execution={"taskSupport": "optional"})
def greet(name: str) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": f"Hello, {name}"}],
        "structuredContent": {"greeting": name},
    }


@prompt_registry.register(description="Generate a short release summary.")
def release_summary(service: str) -> str:
    return f"Summarize the latest release for {service} in three bullets."


@resource_registry.register(
    uri="memo://release-plan",
    name="release_plan",
    description="Current release checklist",
    mime_type="text/markdown",
)
def release_plan() -> str:
    return "# Release Plan\n- freeze API\n- tag build\n"


app = create_app(
    roots=[{"uri": "file:///workspace", "name": "workspace"}],
    server_settings=ServerSettings(
        name="demo-server",
        version="0.1.0",
        capabilities=CapabilitySettings(
            resources_subscribe=True,
            roots_enabled=True,
            tasks_enabled=True,
        ),
    ),
)
```

## Running Over HTTP

`create_app()` returns a FastAPI app with:

- `GET /` for basic server metadata
- Streamable HTTP mounted at `/mcp`

Run it with Uvicorn:

```python
import uvicorn

from my_server import app


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8088, timeout_graceful_shutdown=2)
```

## Running Over Stdio

Use stdio when the MCP host starts your server as a subprocess:

```python
from pymcp import create_app, run_stdio_server


app = create_app()


if __name__ == "__main__":
    run_stdio_server(app)
```

## Registries And App Scope

The package-level registries are copied into an app-scoped registry manager when `create_app()` runs. That means:

- register against the global registries before app construction for simple projects
- or mutate the app-scoped registries later through `pymcp.registry.get_registry_manager(app)`

This keeps multiple app instances isolated from each other after startup.

## Roots And Resources

Roots are configured on app creation:

```python
app = create_app(
    roots=[
        {"uri": "file:///workspace", "name": "workspace"},
        {"uri": "file:///workspace/docs", "name": "docs"},
    ]
)
```

Resources can be listed, read, subscribed to, and unsubscribed from through the built-in handlers. If `CapabilitySettings.resources_subscribe` is left enabled, clients can receive `notifications/resources/updated` when subscribed resources change.

## Example Server

See `example/run_server.py` in the repository root for a complete example with tools, prompts, resources, middleware, and server settings.

## Next Guides

- [Middleware](middleware.md)
- [Tasks](tasks.md)
- [Security](security.md)
- [Runtime Surface](runtime-surface.md)
