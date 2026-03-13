# PyMCP Kit

[![Python CI](https://github.com/Agent-Hellboy/py-mcp/actions/workflows/python-ci.yml/badge.svg)](https://github.com/Agent-Hellboy/py-mcp/actions/workflows/python-ci.yml)
[![codecov](https://codecov.io/gh/Agent-Hellboy/py-mcp/graph/badge.svg)](https://codecov.io/gh/Agent-Hellboy/py-mcp)
[![PyPI - Version](https://img.shields.io/pypi/v/pymcp-kit.svg)](https://pypi.org/project/pymcp-kit/)
[![PyPI Downloads](https://static.pepy.tech/badge/pymcp-kit)](https://pepy.tech/projects/pymcp-kit)
[![Docs](https://img.shields.io/badge/docs-github%20pages-0f766e.svg)](https://agent-hellboy.github.io/py-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

[Documentation](https://agent-hellboy.github.io/py-mcp/) | [Quick Start](https://agent-hellboy.github.io/py-mcp/getting-started/) | [Tasks](https://agent-hellboy.github.io/py-mcp/tasks/) | [Security](https://agent-hellboy.github.io/py-mcp/security/) | [Middleware](https://agent-hellboy.github.io/py-mcp/middleware/)

`PyMCP Kit` is a capability-first MCP server toolkit for FastAPI. It keeps the built-in transport surface small, supports Streamable HTTP and stdio, and ships app-scoped registries, roots, tasks, and optional auth hooks without pulling in a larger framework.

## Quick Start

Install from PyPI:

```bash
pip install pymcp-kit
```

For local development from this repo:

```bash
pip install -e .
```

Register tools, prompts, and resources, then build an app:

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
    return str(a + b)


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
        version="0.1.0",
        capabilities=CapabilitySettings(
            advertise_empty_prompts=False,
            advertise_empty_resources=False,
        ),
    )
)
```

The HTTP transport is mounted at `/mcp`. For local-process integrations, use `run_stdio_server(app)`.

Hosted documentation is built from `docs/` with MkDocs Material and published to GitHub Pages.

## Features

- Streamable HTTP transport for networked MCP servers
- Stdio transport for local-process MCP hosts
- Tool, prompt, and resource registries
- Roots, resource subscriptions, and app-scoped session lifecycle
- Task-aware tool execution with progress, cancellation, and result polling
- Optional authentication and authorization hooks
- Capability advertising through `CapabilitySettings`
- FastAPI middleware integration through `MiddlewareConfig`
- Small surface area focused on practical MCP server builds

## Supported MCP Methods

- `initialize`, `ping`, `notifications/initialized`, and `notifications/cancelled`
- `tools/list` and `tools/call`
- `prompts/list` and `prompts/get`
- `resources/list`, `resources/read`, `resources/subscribe`, and `resources/unsubscribe`
- `roots/list`
- `tasks/list`, `tasks/get`, `tasks/cancel`, and `tasks/result`

## Example Server

Run the bundled example server:

```bash
python example/run_server.py
```

That starts a FastAPI app on `http://127.0.0.1:8088` with the MCP endpoint mounted at `http://127.0.0.1:8088/mcp`.

## Stdio Transport

```python
from pymcp import create_app, run_stdio_server


app = create_app()
run_stdio_server(app)
```

## Middleware

Middleware stays separate from capability registration. Use `MiddlewareConfig` to control CORS, compression, logging, auth hooks, and custom ASGI middleware, then pass it into `create_app()`. See the hosted [Middleware guide](https://agent-hellboy.github.io/py-mcp/middleware/) for examples.

## Scope

- Prompts and resources are advertised only when registered by default
- Registries are copied into an app-scoped manager when `create_app()` runs
- Streamable HTTP and stdio are the only built-in transports
- Extra transports such as SSE and HTTP NDJSON are intentionally not shipped in `pymcp-kit`
