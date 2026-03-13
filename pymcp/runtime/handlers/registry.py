"""Decorator-based JSON-RPC handler registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol, TypeVar

from ..types import DispatchContext, DispatchResult


class HandlerProtocol(Protocol):
    async def handle(self, ctx: DispatchContext) -> DispatchResult:
        ...


HandlerFunc = Callable[[DispatchContext], Awaitable[DispatchResult]]


@dataclass(frozen=True)
class FunctionHandler:
    func: HandlerFunc

    async def handle(self, ctx: DispatchContext) -> DispatchResult:
        return await self.func(ctx)


_HANDLERS: dict[str, HandlerProtocol] = {}
_T = TypeVar("_T", bound=HandlerFunc | HandlerProtocol)


def rpc_method(method: str) -> Callable[[_T], _T]:
    def decorator(handler: _T) -> _T:
        if method in _HANDLERS:
            raise RuntimeError(f"Duplicate handler registration for method '{method}'")
        if hasattr(handler, "handle"):
            resolved = handler
        else:
            resolved = FunctionHandler(handler)  # type: ignore[arg-type]
        _HANDLERS[method] = resolved
        return handler

    return decorator


def get_registered_handler(method: str) -> HandlerProtocol | None:
    return _HANDLERS.get(method)


def get_registered_handlers() -> dict[str, HandlerProtocol]:
    return dict(_HANDLERS)


__all__ = ["get_registered_handler", "get_registered_handlers", "rpc_method"]
