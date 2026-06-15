"""HTTP entrypoints for PyMCP Kit."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .session import get_session_manager
from .settings import ServerSettings
from .transport.streamable_http import router as streamable_http_router


router = APIRouter()
router.include_router(streamable_http_router)


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
    server = {
        "name": settings.name,
        "version": settings.version,
    }
    if settings.title is not None:
        server["title"] = settings.title
    if settings.description is not None:
        server["description"] = settings.description
    if settings.website_url is not None:
        server["websiteUrl"] = settings.website_url
    if settings.icons is not None:
        server["icons"] = settings.icons
    return {
        "status": "ok",
        "server": server,
        "transport": {
            "streamableHttp": "/mcp",
            "stdio": True,
        },
    }


__all__ = ["router"]
