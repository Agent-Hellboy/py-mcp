"""HTTP and SSE endpoints for py-mcp."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .runtime.dispatch import process_jsonrpc_message
from .runtime.payloads import INVALID_REQUEST
from .session import get_session_manager, get_session_store
from .settings import ServerSettings


router = APIRouter()


def _server_settings(app) -> ServerSettings:
    if not hasattr(app.state, "server_settings"):
        app.state.server_settings = ServerSettings()
    return app.state.server_settings


def get_sessions(app):
    """Compatibility shim for the original public helper."""
    manager = get_session_manager(app)
    return {
        session.session_id: {
            "initialized": session.initialized,
            "queue": session.queue,
        }
        for session in manager.list_sessions()
    }


@router.get("/")
async def root(request: Request):
    settings = _server_settings(request.app)
    return {
        "status": "ok",
        "server": {"name": settings.name, "version": settings.version},
        "transport": {
            "sse": "/sse-cursor",
            "message": "/message?sessionId=<id>",
        },
    }


@router.get("/mcp")
async def mcp_root(request: Request):
    return await root(request)


@router.get("/sse-cursor")
@router.get("/mcp/sse")
async def sse_cursor(request: Request):
    session = get_session_store(request.app).create_session()

    async def event_stream():
        yield f"event: endpoint\ndata: /message?sessionId={session.session_id}\n\n"
        while True:
            if await request.is_disconnected():
                get_session_store(request.app).close_session(session.session_id)
                break
            try:
                message = await asyncio.wait_for(session.queue.get(), timeout=10)
                yield f"event: message\ndata: {message}\n\n"
            except asyncio.TimeoutError:
                yield "event: heartbeat\ndata: ping\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/message")
@router.post("/mcp/messages")
async def message(request: Request):
    session_id = request.query_params.get("sessionId")
    session_store = get_session_store(request.app)
    session = session_store.get_session(session_id) if session_id else None
    if session is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Invalid or missing sessionId"},
        )

    try:
        data = await request.json()
    except Exception:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": INVALID_REQUEST, "message": "Invalid JSON-RPC request"},
            },
        )

    if not isinstance(data, dict):
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": INVALID_REQUEST, "message": "Invalid JSON-RPC request"},
            },
        )

    result = await process_jsonrpc_message(
        session_id,
        data,
        app=request.app,
        direct_response=False,
    )
    if result.payload is None:
        return Response(status_code=result.status)
    return JSONResponse(status_code=result.status, content=result.payload)


__all__ = ["router"]
