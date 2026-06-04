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

from .observability.logging import DEFAULT_FORMAT, configure_logging, get_logger
from .protocol.errors import MCPErrorCode, build_error_response
from .protocol.json_types import JSONObject, RPCId
from .security.authn import AllowAnonymousAuthenticator, AuthenticationError, Authenticator
from .security.authz import AllowAllAuthorizer, AuthorizationError, Authorizer, build_authz_request
from .security.oauth import (
    OAuthProtectedResourceConfig,
    build_www_authenticate,
    canonical_resource_uri,
)
from .transport.http_common import try_parse_json_body


logger = get_logger(__name__)


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
        oauth: OAuthProtectedResourceConfig | None = None,
    ):
        super().__init__(app)
        self._authenticator = authenticator
        self._authorizer = authorizer
        self._require_authentication = require_authentication
        self._exempt_paths = set(exempt_paths or [])
        self._oauth = oauth

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.method == "OPTIONS"
            or request.url.path in self._exempt_paths
            or request.url.path.startswith("/.well-known/oauth-protected-resource")
        ):
            logger.debug("[HTTP][AUTH][SKIP] method=%s path=%s", request.method, request.url.path)
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

        authz_request = build_authz_request(
            http_method=request.method,
            path=request.url.path,
            rpc_method=rpc_method,
            params=params,
        )

        try:
            principal = await self._authenticator.authenticate(request)
        except AuthenticationError as exc:
            logger.debug(
                "[HTTP][AUTH][FAILED] method=%s path=%s rpc_method=%s reason=%s",
                request.method,
                request.url.path,
                rpc_method,
                exc,
            )
            headers = self._auth_challenge_headers(
                request,
                scopes=self._required_scopes_for(None, authz_request),
                error="invalid_token",
                error_description=str(exc),
            )
            return JSONResponse(
                status_code=401,
                content=build_error_response(rpc_id, MCPErrorCode.UNAUTHORIZED, str(exc)),
                headers=headers,
            )

        if self._require_authentication and principal is None:
            logger.debug(
                "[HTTP][AUTH][REQUIRED] method=%s path=%s rpc_method=%s",
                request.method,
                request.url.path,
                rpc_method,
            )
            headers = self._auth_challenge_headers(
                request,
                scopes=self._required_scopes_for(None, authz_request),
            )
            return JSONResponse(
                status_code=401,
                content=build_error_response(rpc_id, MCPErrorCode.UNAUTHORIZED, "Authentication required"),
                headers=headers,
            )

        request.state.principal = principal

        try:
            self._authorizer.authorize(principal, authz_request)
        except AuthorizationError as exc:
            scopes = exc.required_scopes or self._required_scopes_for(principal, authz_request)
            logger.debug(
                "[HTTP][AUTHZ][DENY] method=%s path=%s rpc_method=%s subject=%s scopes=%s reason=%s",
                request.method,
                request.url.path,
                rpc_method,
                getattr(principal, "subject", None),
                ",".join(scopes),
                exc,
            )
            headers = self._auth_challenge_headers(
                request,
                scopes=scopes,
                error="insufficient_scope" if scopes else None,
                error_description=str(exc) if scopes else None,
            )
            return JSONResponse(
                status_code=403,
                content=build_error_response(rpc_id, MCPErrorCode.FORBIDDEN, str(exc)),
                headers=headers,
            )

        logger.debug(
            "[HTTP][AUTHZ][ALLOW] method=%s path=%s rpc_method=%s subject=%s",
            request.method,
            request.url.path,
            rpc_method,
            getattr(principal, "subject", None),
        )
        return await call_next(request)

    def _required_scopes_for(self, principal, authz_request) -> tuple[str, ...]:
        get_required_scopes = getattr(self._authorizer, "required_scopes_for", None)
        if not callable(get_required_scopes):
            return ()
        scopes = get_required_scopes(principal, authz_request)
        if not scopes:
            return ()
        return tuple(str(scope) for scope in scopes if str(scope))

    def _auth_challenge_headers(
        self,
        request: Request,
        *,
        scopes: Sequence[str] | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ) -> dict[str, str]:
        if self._oauth is None:
            return {}
        return {
            "WWW-Authenticate": build_www_authenticate(
                request,
                scopes=scopes,
                error=error,
                error_description=error_description,
            )
        }


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
        oauth: OAuthProtectedResourceConfig | None = None,
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
        self.oauth = oauth


async def _oauth_protected_resource_metadata(request: Request, resource_path: str = "") -> JSONResponse:
    config = getattr(request.app.state, "oauth_protected_resource", None)
    if config is None:
        logger.debug("[HTTP][AUTH][DISCOVERY] metadata_not_configured path=%s", request.url.path)
        return JSONResponse(status_code=404, content={"error": "OAuth protected resource metadata not configured"})
    path = f"/{resource_path}" if resource_path else "/mcp"
    logger.debug("[HTTP][AUTH][DISCOVERY] path=%s resource_path=%s", request.url.path, path)
    return JSONResponse(content=config.metadata(resource=canonical_resource_uri(request, path=path)))


def setup_middleware(app: FastAPI, config: MiddlewareConfig) -> None:
    """Apply middleware to the FastAPI app based on the provided config."""

    configure_logging(
        level=config.logging.get("level"),
        fmt=config.logging.get("format", DEFAULT_FORMAT),
    )

    authenticator = config.authn or AllowAnonymousAuthenticator()
    authorizer = config.authz or AllowAllAuthorizer()
    if config.oauth is not None:
        app.state.oauth_protected_resource = config.oauth
        app.add_api_route(
            "/.well-known/oauth-protected-resource",
            _oauth_protected_resource_metadata,
            methods=["GET"],
        )
        app.add_api_route(
            "/.well-known/oauth-protected-resource/{resource_path:path}",
            _oauth_protected_resource_metadata,
            methods=["GET"],
        )
    if config.authn is not None or config.authz is not None or config.require_authn:
        app.state.authenticator = authenticator
        app.state.authorizer = authorizer
        app.add_middleware(
            SecurityMiddleware,
            authenticator=authenticator,
            authorizer=authorizer,
            require_authentication=config.require_authn,
            exempt_paths=config.auth_exempt_paths,
            oauth=config.oauth,
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
    "OAuthProtectedResourceConfig",
    "SecurityMiddleware",
    "setup_middleware",
]
