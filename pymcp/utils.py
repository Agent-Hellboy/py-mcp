"""Compatibility helpers."""

from __future__ import annotations

from fastapi import FastAPI

from .registries.registry import get_registry_manager
from .runtime.dispatch import process_jsonrpc_message
from .session.store import SessionManager
from .session.types import Session, SessionState
from .settings import ServerSettings


def _init_app_state(app: FastAPI) -> None:
    """Initialize app state used by the dispatcher."""
    if not hasattr(app.state, "server_settings"):
        app.state.server_settings = ServerSettings()
    if not hasattr(app.state, "session_manager"):
        app.state.session_manager = SessionManager()
    get_registry_manager(app)  # ensures registry_manager with copy from globals


async def handle_rpc_method(method, data, session_id, rpc_id, sessions):
    """Compatibility shim for older imports.

    This mirrors the old helper signature while delegating to the new dispatcher.
    """
    raw_session = sessions[session_id]
    payload = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    payload.update(data)
    app = FastAPI()
    _init_app_state(app)
    session = Session(
        session_id=session_id,
        queue=raw_session["queue"],
        initialized=raw_session.get("initialized", False),
        client_ready=raw_session.get("client_ready", False),
        protocol_version=raw_session.get("protocol_version"),
        client_capabilities=raw_session.get("client_capabilities", {}),
        client_info=raw_session.get("client_info", {}),
        lifecycle_state=(
            SessionState.READY
            if raw_session.get("client_ready", False)
            else SessionState.WAIT_INITIALIZED
            if raw_session.get("initialized", False)
            else SessionState.WAIT_INIT
        ),
    )
    app.state.session_manager.attach_session(session)
    result = await process_jsonrpc_message(session_id, payload, app=app, direct_response=False)
    raw_session["initialized"] = session.initialized
    raw_session["client_ready"] = session.client_ready
    raw_session["protocol_version"] = session.protocol_version
    raw_session["client_capabilities"] = session.client_capabilities
    raw_session["client_info"] = session.client_info
    return result.payload
