"""Streamable HTTP transport routes."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..runtime.dispatch import process_jsonrpc_message
from ..runtime.payloads import (
    FORBIDDEN,
    INVALID_PARAMS,
    INVALID_REQUEST,
    PARSE_ERROR,
    SESSION_NOT_FOUND,
    error_response,
)
from ..session import get_session_store
from ..settings import SUPPORTED_PROTOCOL_VERSIONS
from .http_common import accept_contains, get_mcp_session_id, try_parse_json_body


router = APIRouter()

_DEFAULT_ALLOWED_ORIGINS = frozenset(
    {
        "http://localhost",
        "http://127.0.0.1",
        "http://[::1]",
    }
)


def _allowed_origins() -> frozenset[str]:
    raw = os.getenv("MCP_ALLOWED_ORIGINS") or os.getenv("PYMCP_ALLOWED_ORIGINS")
    if not raw:
        return _DEFAULT_ALLOWED_ORIGINS
    return frozenset(origin.strip() for origin in raw.split(",") if origin.strip())


def _jsonrpc_http_error(status_code: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_response(None, code, message))


def _reject_invalid_origin(request: Request) -> Response | None:
    origin = request.headers.get("origin")
    if not origin or origin in _allowed_origins():
        return None
    return _jsonrpc_http_error(403, FORBIDDEN, f"Forbidden origin: {origin}")


def _reject_invalid_protocol_version(request: Request) -> Response | None:
    version = request.headers.get("MCP-Protocol-Version")
    if not version:
        return None
    if version in SUPPORTED_PROTOCOL_VERSIONS:
        return None
    supported = ", ".join(SUPPORTED_PROTOCOL_VERSIONS)
    return _jsonrpc_http_error(
        400,
        INVALID_PARAMS,
        f"Unsupported MCP-Protocol-Version '{version}'. Supported: {supported}",
    )


def _stream_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def _post_headers(request: Request, session_id: str) -> dict[str, str]:
    if get_mcp_session_id(request):
        return {}
    return {"MCP-Session-Id": session_id}


def _format_sse(data: str, *, event: str | None = None, event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    for chunk in data.splitlines() or [""]:
        lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


async def _stream_session_events(
    request: Request,
    session_id: str,
    session,
    stream_id: str,
    *,
    heartbeat_interval: float = 10.0,
):
    manager = get_session_store(request.app)
    yield ": connected\n\n"

    counter = 0
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.wait_for(session.queue.get(), timeout=heartbeat_interval)
            except asyncio.TimeoutError:
                yield ": ping\n\n"
                continue

            counter += 1
            yield _format_sse(payload, event="message", event_id=f"{stream_id}:{counter}")
    finally:
        manager.mark_stream_detached(session_id, stream_id)


@router.get("/mcp")
async def mcp_stream(request: Request) -> Response:
    rejected = _reject_invalid_origin(request) or _reject_invalid_protocol_version(request)
    if rejected:
        return rejected
    if not accept_contains(request, "text/event-stream"):
        return Response(status_code=405)

    session_id = get_mcp_session_id(request)
    if not session_id:
        return _jsonrpc_http_error(400, INVALID_PARAMS, "MCP-Session-Id header required")

    manager = get_session_store(request.app)
    session = manager.get_session(session_id)
    if session is None:
        return _jsonrpc_http_error(404, SESSION_NOT_FOUND, "Session not found")

    stream_id = str(uuid4())
    await manager.note_stream_open(
        session_id,
        stream_id=stream_id,
        last_event_id=request.headers.get("Last-Event-ID"),
    )
    return StreamingResponse(
        _stream_session_events(request, session_id, session, stream_id),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )


@router.post("/mcp")
async def mcp_post(request: Request) -> Response:
    rejected = _reject_invalid_origin(request) or _reject_invalid_protocol_version(request)
    if rejected:
        return rejected
    if not accept_contains(request, "application/json"):
        return _jsonrpc_http_error(406, INVALID_PARAMS, "Accept header must include application/json")

    body = await try_parse_json_body(request)
    if body is None:
        return _jsonrpc_http_error(400, PARSE_ERROR, "Parse error")
    if isinstance(body, list):
        return _jsonrpc_http_error(400, INVALID_REQUEST, "Batch JSON-RPC requests are not supported")
    if not isinstance(body, dict):
        return _jsonrpc_http_error(400, INVALID_REQUEST, "Invalid JSON-RPC request")
    data = body

    session_manager = get_session_store(request.app)
    session_id = get_mcp_session_id(request)
    method = data.get("method")
    method_name = method if isinstance(method, str) else None

    if not session_id:
        if method_name != "initialize":
            return _jsonrpc_http_error(400, INVALID_PARAMS, "MCP-Session-Id header required")
        session = session_manager.create_session()
        session_id = session.session_id
    elif session_manager.get_session(session_id) is None:
        return _jsonrpc_http_error(404, SESSION_NOT_FOUND, "Session not found")

    result = await process_jsonrpc_message(
        session_id,
        data,
        app=request.app,
        direct_response=True,
    )
    headers = _post_headers(request, session_id)
    if result.payload is None:
        return Response(status_code=result.status, headers=headers)
    return JSONResponse(status_code=result.status, content=result.payload, headers=headers)


@router.delete("/mcp")
async def mcp_delete(request: Request) -> Response:
    rejected = _reject_invalid_origin(request) or _reject_invalid_protocol_version(request)
    if rejected:
        return rejected

    session_id = get_mcp_session_id(request)
    if not session_id:
        return _jsonrpc_http_error(400, INVALID_PARAMS, "MCP-Session-Id header required")

    manager = get_session_store(request.app)
    if manager.get_session(session_id) is None:
        return _jsonrpc_http_error(404, SESSION_NOT_FOUND, "Session not found")

    await manager.close_session(session_id)
    return Response(status_code=204)


@router.options("/mcp")
async def mcp_options(request: Request) -> Response:
    rejected = _reject_invalid_origin(request)
    if rejected:
        return rejected
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Accept, Content-Type, Last-Event-ID, MCP-Protocol-Version, MCP-Session-Id"
            ),
        },
    )


__all__ = ["router"]
