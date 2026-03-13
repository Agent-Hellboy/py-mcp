"""Authorization policy interfaces for MCP servers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, TypeAlias, TypeVar

from ..protocol.json_types import JSONObject
from .authn import Principal


class AuthorizationError(Exception):
    """Raised when a request is not authorized."""


@dataclass(frozen=True)
class AuthzRequest:
    """Minimal context used by authorization policies."""

    http_method: str | None = None
    path: str | None = None
    rpc_method: str | None = None
    params: JSONObject | None = None
    capability: str | None = None
    tool_name: str | None = None
    prompt_name: str | None = None
    resource_uri: str | None = None
    resource_uris: Sequence[str] | None = None


_PrincipalT_contra = TypeVar("_PrincipalT_contra", bound=Principal, contravariant=True)


class AuthorizerProtocol(Protocol[_PrincipalT_contra]):
    """Authorization hook + discovery filtering."""

    def authorize(self, principal: _PrincipalT_contra | None, request: AuthzRequest) -> None:
        ...

    def filter_capabilities(
        self,
        principal: _PrincipalT_contra | None,
        capabilities: JSONObject,
    ) -> JSONObject:
        ...

    def filter_tools(
        self,
        principal: _PrincipalT_contra | None,
        tools: Sequence[JSONObject],
    ) -> list[JSONObject]:
        ...

    def filter_prompts(
        self,
        principal: _PrincipalT_contra | None,
        prompts: Sequence[JSONObject],
    ) -> list[JSONObject]:
        ...

    def filter_resources(
        self,
        principal: _PrincipalT_contra | None,
        resources: Sequence[JSONObject],
    ) -> list[JSONObject]:
        ...


Authorizer: TypeAlias = AuthorizerProtocol[Principal]


def infer_capability(method: str | None) -> str | None:
    if not method or "/" not in method:
        return None
    prefix = method.split("/", 1)[0]
    return prefix or None


def build_authz_request(
    *,
    rpc_method: str | None,
    params: JSONObject | None = None,
    http_method: str | None = None,
    path: str | None = None,
) -> AuthzRequest:
    tool_name = None
    prompt_name = None
    resource_uri = None
    resource_uris = None

    if rpc_method and isinstance(params, dict):
        if rpc_method == "tools/call":
            name = params.get("name")
            tool_name = name if isinstance(name, str) else None
        elif rpc_method == "prompts/get":
            name = params.get("name")
            prompt_name = name if isinstance(name, str) else None
        elif rpc_method == "resources/read":
            uri = params.get("uri")
            resource_uri = uri if isinstance(uri, str) else None
        elif rpc_method in {"resources/subscribe", "resources/unsubscribe"}:
            uris: list[str] = []
            raw_uris = params.get("uris")
            if isinstance(raw_uris, list):
                uris.extend(entry for entry in raw_uris if isinstance(entry, str))
            raw_uri = params.get("uri")
            if isinstance(raw_uri, str):
                uris.append(raw_uri)
            if uris:
                resource_uris = list(dict.fromkeys(uris))

    return AuthzRequest(
        http_method=http_method,
        path=path,
        rpc_method=rpc_method,
        params=params,
        capability=infer_capability(rpc_method),
        tool_name=tool_name,
        prompt_name=prompt_name,
        resource_uri=resource_uri,
        resource_uris=resource_uris,
    )


class AllowAllAuthorizer:  # pylint: disable=too-few-public-methods,unused-argument
    """Authorization policy that allows all requests."""

    def authorize(self, principal: Principal | None, request: AuthzRequest) -> None:
        return

    def filter_capabilities(self, principal: Principal | None, capabilities: JSONObject) -> JSONObject:
        return dict(capabilities)

    def filter_tools(self, principal: Principal | None, tools: Sequence[JSONObject]) -> list[JSONObject]:
        return list(tools)

    def filter_prompts(self, principal: Principal | None, prompts: Sequence[JSONObject]) -> list[JSONObject]:
        return list(prompts)

    def filter_resources(
        self,
        principal: Principal | None,
        resources: Sequence[JSONObject],
    ) -> list[JSONObject]:
        return list(resources)


class DenyAllAuthorizer:  # pylint: disable=too-few-public-methods,unused-argument
    """Authorization policy that denies all requests."""

    def __init__(self, reason: str = "access denied"):
        self._reason = reason

    def authorize(self, principal: Principal | None, request: AuthzRequest) -> None:
        raise AuthorizationError(self._reason)

    def filter_capabilities(self, principal: Principal | None, capabilities: JSONObject) -> JSONObject:
        return {}

    def filter_tools(self, principal: Principal | None, tools: Sequence[JSONObject]) -> list[JSONObject]:
        return []

    def filter_prompts(self, principal: Principal | None, prompts: Sequence[JSONObject]) -> list[JSONObject]:
        return []

    def filter_resources(
        self,
        principal: Principal | None,
        resources: Sequence[JSONObject],
    ) -> list[JSONObject]:
        return []


class MethodAllowListAuthorizer:  # pylint: disable=too-few-public-methods,unused-argument
    """Allow only specific MCP methods."""

    def __init__(self, allowed_methods: Sequence[str], *, allow_non_rpc: bool = True):
        self._allowed = set(allowed_methods)
        self._allow_non_rpc = allow_non_rpc

    def authorize(self, principal: Principal | None, request: AuthzRequest) -> None:
        if request.rpc_method is None:
            if self._allow_non_rpc:
                return
            raise AuthorizationError(f"rpc method required for: {request.http_method} {request.path}")
        if request.rpc_method not in self._allowed:
            raise AuthorizationError(f"method not allowed: {request.rpc_method}")

    def filter_capabilities(self, principal: Principal | None, capabilities: JSONObject) -> JSONObject:
        return dict(capabilities)

    def filter_tools(self, principal: Principal | None, tools: Sequence[JSONObject]) -> list[JSONObject]:
        return list(tools)

    def filter_prompts(self, principal: Principal | None, prompts: Sequence[JSONObject]) -> list[JSONObject]:
        return list(prompts)

    def filter_resources(
        self,
        principal: Principal | None,
        resources: Sequence[JSONObject],
    ) -> list[JSONObject]:
        return list(resources)


__all__ = [
    "AllowAllAuthorizer",
    "AuthorizationError",
    "Authorizer",
    "AuthzRequest",
    "DenyAllAuthorizer",
    "MethodAllowListAuthorizer",
    "build_authz_request",
    "infer_capability",
]
