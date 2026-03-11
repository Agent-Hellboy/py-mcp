# Middleware Guide

`py-mcp` keeps middleware separate from capability registration. Compression, CORS, and custom headers should be configured at the app edge, not inside the runtime dispatcher or the app-scoped registry/session layers.

The default HTTP transport is Streamable HTTP mounted at `/mcp`. If you need local-process MCP, use the stdio runner from `pymcp.transport`.

## Basic setup

```python
from pymcp import create_app
from pymcp.middleware import MiddlewareConfig


config = MiddlewareConfig(
    cors={
        "allow_origins": ["https://myapp.com"],
        "allow_methods": ["GET", "POST"],
        "allow_headers": ["*"],
        "allow_credentials": True,
    },
    compression={"enabled": True},
)

app = create_app(middleware_config=config)
```

## Custom middleware

```python
class RequestTagMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-server-shape"] = b"py-mcp"
                message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)


config = MiddlewareConfig(custom=[RequestTagMiddleware])
app = create_app(middleware_config=config)
```

## Server identity and capability advertising

```python
from pymcp import CapabilitySettings, ServerSettings, create_app

app = create_app(
    server_settings=ServerSettings(
        name="ops-server",
        version="0.2.0",
        capabilities=CapabilitySettings(
            advertise_empty_prompts=False,
            advertise_empty_resources=False,
        ),
    )
)
```

Use that when you want to control what `initialize` advertises without changing middleware behavior.

## Defaults

- CORS is open by default
- Compression is off by default
- Custom middleware is applied in the order provided
- No logging handlers are installed automatically

## Recommended split

- Keep `MiddlewareConfig` in `config.py`
- Keep capability registrations near the domain logic they wrap
- Let `create_app()` assemble the app-scoped registry manager and session manager
- Keep HTTP transport concerns inside the mounted `/mcp` endpoint
- Use `run_stdio_server(app)` when embedding the server in a stdio-based host
- Keep `run_server.py` thin
