"""Middleware configuration and setup for the MCP framework."""

from __future__ import annotations

from typing import Sequence

from typing_extensions import TypedDict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp

from .observability.logging import DEFAULT_FORMAT, configure_logging
from .protocol.errors import MCPErrorCode, build_error_response
from .protocol.json_types import JSONObject, RPCId
from .security.authn import AllowAnonymousAuthenticator, AuthenticationError, Authenticator
from .security.authz import AllowAllAuthorizer, AuthorizationError, Authorizer, build_authz_request
from .transport.http_common import try_parse_json_body


class CorsConfigInput(TypedDict, total=False):
    allow_origins: list[str]
    allow_credentials: bool
    allow_methods: list[str]
    allow_headers: list[str]


class LoggingConfigInput(TypedDict, total=False):
    level: str
    format: str


class CompressionConfigInput(TypedDict, total=False):
    enabled: bool


class ErrorHandlingConfig(TypedDict, total=False):
    enabled: bool


class SecurityMiddleware(BaseHTTPMiddleware):
    """Authenticate and authorize inbound requests."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        authenticator: Authenticator,
        authorizer: Authorizer,
        require_authentication: bool = False,
        exempt_paths: Sequence[str] | None = None,
    ):
        super().__init__(app)
        self._authenticator = authenticator
        self._authorizer = authorizer
        self._require_authentication = require_authentication
        self._exempt_paths = set(exempt_paths or [])

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS" or request.url.path in self._exempt_paths:
            return await call_next(request)

        rpc_id: RPCId = None
        rpc_method: str | None = None
        params: JSONObject | None = None

        if request.method == "POST":
            body_data = await try_parse_json_body(request)
            if isinstance(body_data, dict):
                raw_method = body_data.get("method")
                rpc_method = raw_method if isinstance(raw_method, str) else None
                if "id" in body_data:
                    raw_id = body_data.get("id")
                    rpc_id = raw_id if isinstance(raw_id, (str, int)) or raw_id is None else None
                raw_params = body_data.get("params")
                params = raw_params if isinstance(raw_params, dict) else None

        try:
            principal = await self._authenticator.authenticate(request)
        except AuthenticationError as exc:
            return JSONResponse(
                status_code=401,
                content=build_error_response(rpc_id, MCPErrorCode.UNAUTHORIZED, str(exc)),
            )

        if self._require_authentication and principal is None:
            return JSONResponse(
                status_code=401,
                content=build_error_response(rpc_id, MCPErrorCode.UNAUTHORIZED, "Authentication required"),
            )

        request.state.principal = principal

        authz_request = build_authz_request(
            http_method=request.method,
            path=request.url.path,
            rpc_method=rpc_method,
            params=params,
        )
        try:
            self._authorizer.authorize(principal, authz_request)
        except AuthorizationError as exc:
            return JSONResponse(
                status_code=403,
                content=build_error_response(rpc_id, MCPErrorCode.FORBIDDEN, str(exc)),
            )

        return await call_next(request)


class MiddlewareConfig:
    """Configuration class for setting up middleware in the MCP server."""

    def __init__(
        self,
        cors: CorsConfigInput | None = None,
        logging: LoggingConfigInput | None = None,
        error_handling: ErrorHandlingConfig | None = None,
        compression: CompressionConfigInput | None = None,
        custom: Sequence[type] | None = None,
        authn: Authenticator | None = None,
        authz: Authorizer | None = None,
        require_authn: bool = False,
        auth_exempt_paths: Sequence[str] | None = None,
    ):
        self.cors = cors or {
            "allow_origins": ["*"],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
        self.logging = logging or {
            "level": "INFO",
            "format": DEFAULT_FORMAT,
        }
        self.error_handling = error_handling or {}
        self.compression = compression or {"enabled": False}
        self.custom = list(custom or [])
        self.authn = authn
        self.authz = authz
        self.require_authn = require_authn
        self.auth_exempt_paths = list(auth_exempt_paths or ["/", "/health"])


def setup_middleware(app: FastAPI, config: MiddlewareConfig) -> None:
    """Apply middleware to the FastAPI app based on the provided config."""

    configure_logging(
        level=config.logging.get("level"),
        fmt=config.logging.get("format", DEFAULT_FORMAT),
    )

    authenticator = config.authn or AllowAnonymousAuthenticator()
    authorizer = config.authz or AllowAllAuthorizer()
    if config.authn is not None or config.authz is not None or config.require_authn:
        app.state.authenticator = authenticator
        app.state.authorizer = authorizer
        app.add_middleware(
            SecurityMiddleware,
            authenticator=authenticator,
            authorizer=authorizer,
            require_authentication=config.require_authn,
            exempt_paths=config.auth_exempt_paths,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors["allow_origins"],
        allow_credentials=config.cors["allow_credentials"],
        allow_methods=config.cors["allow_methods"],
        allow_headers=config.cors["allow_headers"],
    )

    if config.compression.get("enabled", False):
        app.add_middleware(GZipMiddleware)

    for middleware in config.custom:
        if not callable(middleware):
            raise ValueError(f"Custom middleware {middleware} is not callable")
        app.add_middleware(middleware)


__all__ = [
    "CompressionConfigInput",
    "CorsConfigInput",
    "ErrorHandlingConfig",
    "LoggingConfigInput",
    "MiddlewareConfig",
    "SecurityMiddleware",
    "setup_middleware",
]
