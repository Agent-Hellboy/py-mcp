"""Streamable HTTP transport routes."""

from __future__ import annotations

import json
import os
from asyncio import TimerHandle, get_running_loop
from urllib.parse import urlparse
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
from ..observability.logging import get_logger
from ..session import get_session_store
from ..session.queueing import log_client_follow_up_request
from ..session.types import Session
from ..settings import SUPPORTED_PROTOCOL_VERSIONS
from .http_common import accept_contains, get_mcp_session_id, try_parse_json_body
from .shutdown import ensure_shutdown_event, wait_queue_message


router = APIRouter()
logger = get_logger(__name__)
_CONNECTION_COMPLETE_IDLE_SECONDS = 1.0

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


def _is_loopback_origin(origin: str) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme != "http":
        return False
    hostname = (parsed.hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _jsonrpc_http_error(status_code: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_response(None, code, message))


def _reject_invalid_origin(request: Request) -> Response | None:
    origin = request.headers.get("origin")
    if not origin or origin in _allowed_origins() or _is_loopback_origin(origin):
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


def _log_jsonrpc_start(data: dict, session_id: str, session: Session | None = None) -> None:
    method = data.get("method")
    method_name = method if isinstance(method, str) else "<unknown>"
    if session is not None and method_name != "<unknown>":
        log_client_follow_up_request(session, request_method=method_name)
    if method_name == "initialize":
        logger.info(
            "[HTTP][MCP] server state client connection started session=%s",
            session_id,
        )
        logger.info(
            "[HTTP][MCP] server state handshake started session=%s",
            session_id,
        )
    logger.info(
        "[HTTP][MCP] client -> server request received method=%s session=%s",
        method_name,
        session_id,
    )
    logger.debug(
        "[HTTP][MCP] client -> server request body method=%s session=%s body=%s",
        method_name,
        session_id,
        data,
    )


def _log_jsonrpc_complete(
    method_name: str,
    status: int,
    payload: dict | None,
    session_id: str,
) -> None:
    if method_name == "notifications/initialized" and status == 202:
        logger.info(
            "[HTTP][MCP] server state handshake complete session=%s",
            session_id,
        )
    else:
        logger.info(
            "[HTTP][MCP] server -> client response sent method=%s status=%s session=%s",
            method_name,
            status,
            session_id,
        )
        logger.debug(
            "[HTTP][MCP] server -> client response body method=%s session=%s body=%s",
            method_name,
            session_id,
            payload,
        )


def _schedule_connection_complete(request: Request, session_id: str) -> None:
    handles = getattr(request.app.state, "mcp_connection_complete_handles", None)
    if handles is None:
        handles = {}
        request.app.state.mcp_connection_complete_handles = handles

    existing = handles.pop(session_id, None)
    if isinstance(existing, TimerHandle):
        existing.cancel()

    def _log_complete() -> None:
        handles.pop(session_id, None)
        logger.info(
            "[HTTP][MCP] server state client connection complete session=%s",
            session_id,
        )

    handles[session_id] = get_running_loop().call_later(
        _CONNECTION_COMPLETE_IDLE_SECONDS,
        _log_complete,
    )


def _apply_session_principal(session, request_principal) -> Response | None:
    if request_principal is None:
        return None
    if session.principal is None:
        session.principal = request_principal
        return None
    if session.principal != request_principal:
        return _jsonrpc_http_error(403, FORBIDDEN, "Session principal mismatch")
    return None


def _format_sse(data: str, *, event: str | None = None, event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    for chunk in data.splitlines() or [""]:
        lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource_probe() -> Response:
    logger.info("[HTTP][MCP] client -> server probe oauth-protected-resource metadata")
    return Response(status_code=404)


@router.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_protected_resource_mcp_probe() -> Response:
    logger.info("[HTTP][MCP] client -> server probe oauth-protected-resource metadata for /mcp")
    return Response(status_code=404)


async def _stream_session_events(
    request: Request,
    session_id: str,
    session,
    stream_id: str,
    *,
    last_event_id: str | None = None,
    heartbeat_interval: float = 10.0,
    poll_interval: float = 1.0,
):
    manager = get_session_store(request.app)
    shutdown = ensure_shutdown_event(request.app)
    event_log = session.event_log
    yield ": connected\n\n"

    resume_stream_id, after_seq = event_log.should_resume(last_event_id)
    if resume_stream_id is not None and after_seq is not None:
        for replay_event_id, replay_payload in event_log.replay(resume_stream_id, after_seq):
            yield _format_sse(replay_payload, event="message", event_id=replay_event_id)

    try:
        while True:
            if shutdown.is_set() or await request.is_disconnected():
                break
            outcome, payload = await wait_queue_message(
                session.queue,
                shutdown=shutdown,
                timeout=min(heartbeat_interval, poll_interval),
            )
            if outcome == "shutdown":
                break
            if outcome == "timeout":
                yield ": ping\n\n"
                continue

            event_id = event_log.next_event_id(stream_id)
            event_log.record(event_id, payload, event_type="message")
            try:
                payload_data = json.loads(payload)
                sse_method = payload_data.get("method")
                if isinstance(sse_method, str):
                    logger.info(
                        "[HTTP][MCP] server -> client sse event method=%s session=%s stream=%s event_id=%s",
                        sse_method,
                        session_id,
                        stream_id,
                        event_id,
                    )
            except json.JSONDecodeError:
                logger.debug(
                    "[HTTP][MCP] server -> client sse event session=%s stream=%s event_id=%s non_json_payload=%s",
                    session_id,
                    stream_id,
                    event_id,
                    payload,
                )
            yield _format_sse(payload, event="message", event_id=event_id)
    finally:
        logger.info(
            "[HTTP][MCP] server state sse stream detached session=%s stream=%s",
            session_id,
            stream_id,
        )
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

    last_event_id = request.headers.get("Last-Event-ID")
    resume_stream_id, _ = session.event_log.should_resume(last_event_id)
    stream_id = resume_stream_id or str(uuid4())
    await manager.note_stream_open(
        session_id,
        stream_id=stream_id,
        last_event_id=last_event_id,
    )
    logger.info(
        "[HTTP][MCP] server state sse stream attached session=%s stream=%s",
        session_id,
        stream_id,
    )
    return StreamingResponse(
        _stream_session_events(
            request,
            session_id,
            session,
            stream_id,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers=_stream_headers(),
    )


@router.post("/mcp")
async def mcp_post(request: Request) -> Response:
    rejected = _reject_invalid_origin(request) or _reject_invalid_protocol_version(request)
    if rejected:
        return rejected
    if not (
        accept_contains(request, "application/json")
        and accept_contains(request, "text/event-stream")
    ):
        return _jsonrpc_http_error(
            406,
            INVALID_PARAMS,
            "Accept header must include application/json and text/event-stream",
        )

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
    request_principal = getattr(request.state, "principal", None)

    if not session_id:
        if method_name != "initialize":
            return _jsonrpc_http_error(400, INVALID_PARAMS, "MCP-Session-Id header required")
        session = session_manager.create_session()
        session_id = session.session_id
        principal_error = _apply_session_principal(session, request_principal)
        if principal_error is not None:
            return principal_error
    elif session_manager.get_session(session_id) is None:
        return _jsonrpc_http_error(404, SESSION_NOT_FOUND, "Session not found")
    else:
        session = session_manager.get_session(session_id)
        if session is not None:
            principal_error = _apply_session_principal(session, request_principal)
            if principal_error is not None:
                return principal_error

    _log_jsonrpc_start(data, session_id, session)

    if method_name is None:
        rpc_id = data.get("id")
        if isinstance(rpc_id, str):
            session_manager.resolve_pending_response(session_id, rpc_id, data)
        headers = _post_headers(request, session_id)
        _schedule_connection_complete(request, session_id)
        return Response(status_code=202, headers=headers)

    result = await process_jsonrpc_message(
        session_id,
        data,
        app=request.app,
        direct_response=True,
    )
    _log_jsonrpc_complete(method_name, result.status, result.payload, session_id)
    _schedule_connection_complete(request, session_id)
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
