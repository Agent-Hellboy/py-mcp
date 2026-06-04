import logging

from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.middleware import MiddlewareConfig
from pymcp.security import (
    MethodAllowListAuthorizer,
    OAuthProtectedResourceConfig,
    RuleBasedAuthorizer,
    TokenMapAuthenticator,
)


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


def test_oauth_protected_resource_metadata_route():
    config = MiddlewareConfig(
        oauth=OAuthProtectedResourceConfig(
            authorization_servers=["https://auth.example.com"],
            scopes_supported=["files:read"],
            resource_name="Test MCP",
        )
    )
    app = create_app(middleware_config=config)
    client = TestClient(app)

    response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    assert response.json() == {
        "resource": "http://testserver/mcp",
        "authorization_servers": ["https://auth.example.com"],
        "scopes_supported": ["files:read"],
        "bearer_methods_supported": ["header"],
        "resource_name": "Test MCP",
    }


def test_create_app_kwargs_forward_oauth_config_to_middleware():
    app = create_app(
        middleware_config=None,
        oauth=OAuthProtectedResourceConfig(
            authorization_servers=["https://auth.example.com"],
            scopes_supported=["files:read"],
        ),
    )
    client = TestClient(app)

    response = client.get("/.well-known/oauth-protected-resource")

    assert response.status_code == 200
    assert response.json()["authorization_servers"] == ["https://auth.example.com"]


def test_oauth_authentication_required_response_includes_discovery_challenge():
    app = create_app(
        middleware_config=MiddlewareConfig(
            authn=TokenMapAuthenticator({"secret-token": {"subject": "alice"}}),
            require_authn=True,
            oauth=OAuthProtectedResourceConfig(
                authorization_servers=["https://auth.example.com"],
                scopes_supported=["mcp:access"],
            ),
        )
    )
    client = TestClient(app)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
    )

    assert response.status_code == 401
    challenge = response.headers["WWW-Authenticate"]
    assert challenge.startswith("Bearer ")
    assert 'resource_metadata="http://testserver/.well-known/oauth-protected-resource"' in challenge


def test_oauth_insufficient_scope_response_includes_scope_challenge():
    app = create_app(
        middleware_config=MiddlewareConfig(
            authn=TokenMapAuthenticator(
                {
                    "secret-token": {
                        "subject": "alice",
                        "scopes": ["files:read"],
                    }
                }
            ),
            authz=RuleBasedAuthorizer(
                {
                    "default_effect": "deny",
                    "rules": [
                        {
                            "rpc_method": "initialize",
                            "effect": "allow",
                            "allow_subjects": ["alice"],
                        },
                        {
                            "rpc_method": "ping",
                            "effect": "allow",
                            "allow_scopes": ["files:write"],
                            "message": "Additional file write permission required",
                        },
                    ],
                }
            ),
            require_authn=True,
            oauth=OAuthProtectedResourceConfig(
                authorization_servers=["https://auth.example.com"],
                scopes_supported=["files:read", "files:write"],
            ),
        )
    )
    client = TestClient(app)

    initialize = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer secret-token",
        },
    )
    assert initialize.status_code == 200

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "ping"},
        headers={
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer secret-token",
            "MCP-Session-Id": initialize.headers["MCP-Session-Id"],
        },
    )

    assert response.status_code == 403
    challenge = response.headers["WWW-Authenticate"]
    assert 'error="insufficient_scope"' in challenge
    assert 'scope="files:write"' in challenge
    assert 'resource_metadata="http://testserver/.well-known/oauth-protected-resource"' in challenge
    assert response.json()["error"]["message"] == "Additional file write permission required"
