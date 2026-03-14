# Middleware

`pymcp-kit` keeps HTTP middleware separate from capability registration and runtime dispatch. Configure middleware at the app edge, then let the MCP runtime handle JSON-RPC and session state.

## `MiddlewareConfig`

```python
from pymcp import create_app
from pymcp.middleware import MiddlewareConfig


config = MiddlewareConfig(
    cors={
        "allow_origins": ["https://app.example.com"],
        "allow_methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
        "allow_credentials": True,
    },
    logging={
        "level": "DEBUG",
        "format": "%(asctime)s %(levelname)s %(message)s",
    },
    compression={"enabled": True},
)

app = create_app(middleware_config=config)
```

## Keyword Argument Shortcut

`create_app()` also accepts the same settings directly:

```python
app = create_app(
    cors={
        "allow_origins": ["https://app.example.com"],
        "allow_methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
        "allow_credentials": True,
    },
    logging={"level": "INFO"},
    compression={"enabled": True},
)
```

## Defaults

- CORS defaults to `allow_origins=["*"]`, `allow_methods=["*"]`, `allow_headers=["*"]`
- compression is disabled by default
- logging is configured through `pymcp.observability.logging.configure_logging()`
- custom middleware is applied in the order you pass it
- auth middleware is only installed when `authn`, `authz`, or `require_authn=True` is provided

## Transport-Level Origin Checks

The Streamable HTTP transport has its own origin allowlist in addition to CORS. By default, requests with an `Origin` header are restricted to localhost-style origins.

To allow browser traffic from other origins, set one of:

```bash
export MCP_ALLOWED_ORIGINS=https://app.example.com
```

or

```bash
export PYMCP_ALLOWED_ORIGINS=https://app.example.com
```

Use a comma-separated list for multiple origins.

## Custom Middleware

```python
from pymcp import create_app
from pymcp.middleware import MiddlewareConfig


class RequestTagMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-server-shape", b"pymcp-kit"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


app = create_app(
    middleware_config=MiddlewareConfig(custom=[RequestTagMiddleware])
)
```

## Security Hooks

Security is configured through the same middleware entry point:

- `authn`: authenticator instance
- `authz`: authorizer instance
- `require_authn`: reject unauthenticated requests with `401`
- `auth_exempt_paths`: skip auth middleware on specific HTTP paths

See [Security](./security.md) for concrete examples.
