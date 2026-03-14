"""Authentication hook interfaces for MCP transports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, TypeAlias, TypeVar

from fastapi import Request

from ..protocol.json_types import JSONValue


class AuthenticationError(Exception):
    """Raised when credentials are present but invalid."""


@dataclass(frozen=True)
class Principal:
    """Authenticated identity plus optional authorization attributes."""

    subject: str
    display_name: str | None = None
    scopes: set[str] = field(default_factory=set)
    roles: set[str] = field(default_factory=set)
    claims: Mapping[str, JSONValue] = field(default_factory=dict)


_PrincipalT_co = TypeVar("_PrincipalT_co", bound=Principal, covariant=True)


class AuthenticatorProtocol(Protocol[_PrincipalT_co]):
    """Authentication hook used by middleware/transports."""

    async def authenticate(self, request: Request) -> _PrincipalT_co | None:
        ...


Authenticator: TypeAlias = AuthenticatorProtocol[Principal]


def get_bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip() or None


class AllowAnonymousAuthenticator:  # pylint: disable=too-few-public-methods
    """Default authenticator that treats all requests as anonymous."""

    async def authenticate(self, request: Request) -> Principal | None:  # pylint: disable=unused-argument
        return None


__all__ = [
    "AllowAnonymousAuthenticator",
    "AuthenticationError",
    "Authenticator",
    "Principal",
    "get_bearer_token",
]
