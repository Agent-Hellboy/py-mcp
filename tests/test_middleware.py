import logging

from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.middleware import MiddlewareConfig
from pymcp.security import MethodAllowListAuthorizer


class CustomHeaderMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                headers[b"x-custom-middleware"] = b"true"
                message["headers"] = list(headers.items())
            await send(message)

        await self.app(scope, receive, send_wrapper)


def test_gzip_and_custom_middleware():
    config = MiddlewareConfig(
        compression={"enabled": True},
        custom=[CustomHeaderMiddleware],
    )
    app = create_app(middleware_config=config)

    @app.get("/plain")
    def plain():
        return PlainTextResponse("Hello World!" * 100)

    client = TestClient(app)
    response = client.get("/plain", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert response.headers.get("x-custom-middleware") == "true"


def test_create_app_applies_middleware_logging_level():
    config = MiddlewareConfig(
        logging={
            "level": "DEBUG",
            "format": "%(asctime)s %(levelname)s %(message)s",
        }
    )
    create_app(middleware_config=config)

    assert logging.getLogger("pymcp").getEffectiveLevel() == logging.DEBUG


def test_security_middleware_authorizes_rpc_requests():
    app = create_app(
        middleware_config=None,
        authz=MethodAllowListAuthorizer(["initialize"]),
    )
    client = TestClient(app)

    initialize = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert initialize.status_code == 200
    session_id = initialize.headers["MCP-Session-Id"]

    denied = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
        headers={
            "Accept": "application/json, text/event-stream",
            "MCP-Session-Id": session_id,
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["message"] == "method not allowed: ping"
