"""Transport-agnostic JSON-RPC dispatcher."""

from __future__ import annotations

import logging
from typing import Awaitable, Protocol

from fastapi import FastAPI

from ..registries.registry import get_registry_manager
from ..session.store import SessionManager, get_session_manager
from ..session.types import Session, SessionState
from .handlers.registry import get_registered_handlers
from .payloads import INVALID_REQUEST, JSONRPC_VERSION, METHOD_NOT_FOUND, INTERNAL_ERROR, error_response
from .types import DispatchContext, DispatchResponse, DispatchResult, JSONObject

# Side-effect imports register built-in handlers.
from .handlers import lifecycle as _lifecycle  # noqa: F401
from .handlers import prompts as _prompts  # noqa: F401
from .handlers import resources as _resources  # noqa: F401
from .tools import handlers as _tools  # noqa: F401

BUILTIN_HANDLER_MODULES = (_lifecycle, _prompts, _resources, _tools)
logger = logging.getLogger(__name__)


class DispatchError(Exception):
    def __init__(self, *, status: int, code: int, message: str, rpc_id):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.rpc_id = rpc_id


def _rpc_id_from_data(data: JSONObject):
    raw_id = data.get("id")
    if raw_id is None or (isinstance(raw_id, (str, int)) and not isinstance(raw_id, bool)):
        return raw_id
    return None


class DispatchNext(Protocol):
    def __call__(self, ctx: DispatchContext) -> Awaitable[DispatchResponse]:
        ...


class DispatchMiddleware(Protocol):
    async def __call__(self, ctx: DispatchContext, call_next: DispatchNext) -> DispatchResponse:
        ...


class ErrorBoundaryMiddleware:
    async def __call__(self, ctx: DispatchContext, call_next: DispatchNext) -> DispatchResponse:
        try:
            return await call_next(ctx)
        except Exception:
            logger.exception("Unhandled exception in dispatch pipeline for method %s", ctx.method)
            payload = error_response(
                ctx.rpc_id if "id" in ctx.data else None,
                INTERNAL_ERROR,
                "Internal error",
            )
            await ctx.maybe_enqueue(payload)
            return DispatchResponse(status=200, json=True, payload=payload)


class InitGateMiddleware:
    _POST_INIT_ALLOWED = frozenset({"initialize", "notifications/initialized", "ping"})

    async def __call__(self, ctx: DispatchContext, call_next: DispatchNext) -> DispatchResponse:
        state = ctx.session.lifecycle_state
        if state == SessionState.CLOSED:
            payload = error_response(ctx.rpc_id, INVALID_REQUEST, "Session is closed")
            await ctx.maybe_enqueue(payload)
            return DispatchResponse(status=404, json=True, payload=payload)
        if state == SessionState.WAIT_INIT and ctx.method != "initialize":
            payload = error_response(ctx.rpc_id, INVALID_REQUEST, "server not initialized.")
            await ctx.maybe_enqueue(payload)
            return DispatchResponse(status=200, json=True, payload=payload)
        if state == SessionState.WAIT_INITIALIZED and ctx.method not in self._POST_INIT_ALLOWED:
            payload = error_response(ctx.rpc_id, INVALID_REQUEST, "server not initialized.")
            await ctx.maybe_enqueue(payload)
            return DispatchResponse(status=200, json=True, payload=payload)
        if state == SessionState.READY and ctx.method == "initialize":
            payload = error_response(ctx.rpc_id, INVALID_REQUEST, "server already initialized.")
            await ctx.maybe_enqueue(payload)
            return DispatchResponse(status=200, json=True, payload=payload)
        return await call_next(ctx)


class CapabilityGateMiddleware:
    _PREFIXES = (
        ("tools/", "tools"),
        ("prompts/", "prompts"),
        ("resources/", "resources"),
    )

    async def __call__(self, ctx: DispatchContext, call_next: DispatchNext) -> DispatchResponse:
        for prefix, feature in self._PREFIXES:
            if ctx.method.startswith(prefix) and not ctx.supports(feature):
                payload = error_response(ctx.rpc_id, METHOD_NOT_FOUND, f"{feature} not supported")
                await ctx.maybe_enqueue(payload)
                return DispatchResponse(status=200, json=True, payload=payload)
        return await call_next(ctx)


class Dispatcher:
    def __init__(
        self,
        *,
        handlers: dict[str, object] | None = None,
        middlewares: list[DispatchMiddleware] | None = None,
    ) -> None:
        self._handlers = handlers  # None = use get_registered_handlers() at call time
        self._middlewares = (
            middlewares
            if middlewares is not None
            else [
                ErrorBoundaryMiddleware(),
                InitGateMiddleware(),
                CapabilityGateMiddleware(),
            ]
        )

    @staticmethod
    def _validate_envelope(data: JSONObject) -> tuple[object, str]:
        rpc_id = _rpc_id_from_data(data)
        method = data.get("method")
        if data.get("jsonrpc") != JSONRPC_VERSION or not isinstance(method, str) or not method:
            raise DispatchError(
                status=200,
                code=INVALID_REQUEST,
                message="Invalid JSON-RPC request",
                rpc_id=rpc_id if "id" in data else None,
            )
        return rpc_id, method

    @staticmethod
    def _get_session(
        *,
        session_id: str,
        data: JSONObject,
        app: FastAPI,
    ) -> tuple[SessionManager, Session]:
        session_manager = get_session_manager(app)
        session = session_manager.get_session(session_id)
        if session is None:
            raise DispatchError(
                status=404,
                code=METHOD_NOT_FOUND,
                message="Session not found",
                rpc_id=_rpc_id_from_data(data) if "id" in data else None,
            )
        return session_manager, session

    async def _call_handler(self, ctx: DispatchContext) -> DispatchResponse:
        handlers = self._handlers if self._handlers is not None else get_registered_handlers()
        handler = handlers.get(ctx.method)
        if handler is None:
            payload = error_response(ctx.rpc_id, METHOD_NOT_FOUND, f"Unsupported method '{ctx.method}'")
            await ctx.maybe_enqueue(payload)
            return DispatchResponse(status=200, json=True, payload=payload)
        return await handler.handle(ctx)

    async def _run_pipeline(self, ctx: DispatchContext) -> DispatchResponse:
        async def call_at(index: int, current: DispatchContext) -> DispatchResponse:
            if index >= len(self._middlewares):
                return await self._call_handler(current)
            middleware = self._middlewares[index]
            return await middleware(current, lambda next_ctx: call_at(index + 1, next_ctx))

        return await call_at(0, ctx)

    async def dispatch(
        self,
        *,
        session_id: str,
        data: JSONObject,
        app: FastAPI,
        direct_response: bool = False,
    ) -> DispatchResponse:
        try:
            session_manager, session = self._get_session(session_id=session_id, data=data, app=app)
            rpc_id, method = self._validate_envelope(data)
        except DispatchError as exc:
            payload = error_response(exc.rpc_id, exc.code, exc.message)
            return DispatchResponse(status=exc.status, json=True, payload=payload)

        server_settings = getattr(app.state, "server_settings", None)
        if server_settings is None:
            raise RuntimeError("app.state.server_settings is not set; ensure the app is initialized with create_app")
        ctx = DispatchContext(
            session_id=session_id,
            data=data,
            app=app,
            session=session,
            rpc_id=rpc_id,
            method=method,
            registry_manager=get_registry_manager(app),
            server_settings=server_settings,
            session_manager=session_manager,
            direct_response=direct_response,
        )
        return await self._run_pipeline(ctx)


_dispatcher = Dispatcher()


async def process_jsonrpc_message(
    session_id: str,
    data: JSONObject,
    *,
    app: FastAPI,
    direct_response: bool = False,
) -> DispatchResult:
    return await _dispatcher.dispatch(
        session_id=session_id,
        data=data,
        app=app,
        direct_response=direct_response,
    )


__all__ = ["DispatchError", "Dispatcher", "process_jsonrpc_message"]
