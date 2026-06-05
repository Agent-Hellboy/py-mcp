"""Session notification helpers and registry listener attachment."""

from __future__ import annotations

import json

from fastapi import FastAPI

from ..capabilities.registry import get_server_capabilities
from ..protocol.logging_levels import normalize_log_level, should_send_log
from ..registries.registry import get_registry_manager
from .queueing import (
    log_notification_skipped,
    notification_method,
    record_outbound_notification,
)
from .store import get_session_manager
from .types import Session, SessionState


JSONObject = dict[str, object]


async def send_notification(session: Session | None, notification: JSONObject) -> bool:
    """Queue a notification for a ready session with an attached stream."""

    method = notification_method(notification)
    if session is None:
        log_notification_skipped(method=method, reason="missing_session")
        return False
    if session.lifecycle_state != SessionState.READY:
        log_notification_skipped(method=method, session_id=session.session_id, reason="session_not_ready")
        return False
    if not session.stream_attached:
        log_notification_skipped(method=method, session_id=session.session_id, reason="stream_not_attached")
        return False
    await session.queue.put(json.dumps(notification))
    record_outbound_notification(session, notification)
    return True


def enqueue_notification(session: Session | None, notification: JSONObject) -> bool:
    """Queue a notification without blocking for a ready session with an attached stream."""

    method = notification_method(notification)
    if session is None:
        log_notification_skipped(method=method, reason="missing_session")
        return False
    if session.lifecycle_state != SessionState.READY:
        log_notification_skipped(method=method, session_id=session.session_id, reason="session_not_ready")
        return False
    if not session.stream_attached:
        log_notification_skipped(method=method, session_id=session.session_id, reason="stream_not_attached")
        return False
    try:
        session.queue.put_nowait(json.dumps(notification))
    except Exception:
        log_notification_skipped(method=method, session_id=session.session_id, reason="queue_unavailable")
        return False
    record_outbound_notification(session, notification)
    return True

def attach_prompt_list_changed_notifications(app: FastAPI) -> None:
    """Attach prompt list-changed notifications to the app-scoped prompt registry."""

    prompt_caps = get_server_capabilities(app).get_capabilities().get("prompts")
    if not isinstance(prompt_caps, dict) or not prompt_caps.get("listChanged"):
        return

    session_manager = get_session_manager(app)
    prompt_registry = get_registry_manager(app).get_prompt_registry()

    def notify() -> None:
        session_manager.broadcast_notification({"jsonrpc": "2.0", "method": "notifications/prompts/list_changed"})

    prompt_registry.add_listener(notify)


def attach_tool_list_changed_notifications(app: FastAPI) -> None:
    """Attach tool list-changed notifications to the app-scoped tool registry."""

    tool_caps = get_server_capabilities(app).get_capabilities().get("tools")
    if not isinstance(tool_caps, dict) or not tool_caps.get("listChanged"):
        return

    session_manager = get_session_manager(app)
    tool_registry = get_registry_manager(app).get_tool_registry()

    def notify() -> None:
        session_manager.broadcast_notification({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})

    tool_registry.add_listener(notify)


def attach_resource_list_changed_notifications(app: FastAPI) -> None:
    """Attach resource list-changed notifications to the app-scoped resource registry."""

    resource_caps = get_server_capabilities(app).get_capabilities().get("resources")
    if not isinstance(resource_caps, dict) or not resource_caps.get("listChanged"):
        return

    session_manager = get_session_manager(app)
    resource_registry = get_registry_manager(app).get_resource_registry()

    def notify() -> None:
        session_manager.broadcast_notification(
            {"jsonrpc": "2.0", "method": "notifications/resources/list_changed"}
        )

    resource_registry.add_listener(notify)


def attach_resource_updated_notifications(app: FastAPI) -> None:
    """Attach resource updated notifications to the app-scoped resource registry."""

    resource_caps = get_server_capabilities(app).get_capabilities().get("resources")
    if not isinstance(resource_caps, dict) or not resource_caps.get("subscribe"):
        return

    session_manager = get_session_manager(app)
    resource_registry = get_registry_manager(app).get_resource_registry()

    def notify(uri: str) -> None:
        session_manager.broadcast_resource_update(
            uri,
            {
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": uri},
            },
        )

    resource_registry.add_update_listener(notify)


# ---------------------------------------------------------------------------
# Elicitation completion notification (server -> client)
# ---------------------------------------------------------------------------


async def send_elicitation_complete(
    app: FastAPI,
    session_id: str,
    elicitation_id: str,
) -> bool:
    """Send ``notifications/elicitation/complete`` to the client.

    Used after a URL-mode elicitation's out-of-band interaction finishes.
    """
    manager = get_session_manager(app)
    session = manager.get_session(session_id)
    notification: JSONObject = {
        "jsonrpc": "2.0",
        "method": "notifications/elicitation/complete",
        "params": {"elicitationId": elicitation_id},
    }
    return await send_notification(session, notification)


# ---------------------------------------------------------------------------
# Logging notification (server -> client)
# ---------------------------------------------------------------------------


async def send_log_message(
    app: FastAPI,
    session_id: str,
    level: str,
    logger: str | None = None,
    data: object = None,
) -> bool:
    """Send ``notifications/message`` (structured log) to the client.

    Only sent when the server advertises the ``logging`` capability and the
    message meets the session minimum log level configured via ``logging/setLevel``.
    """
    logging_caps = get_server_capabilities(app).get_capabilities().get("logging")
    if not isinstance(logging_caps, dict):
        return False

    manager = get_session_manager(app)
    session = manager.get_session(session_id)
    if session is None:
        return False

    normalized_level = normalize_log_level(level)
    if normalized_level is None:
        normalized_level = level.strip().lower()
    if not should_send_log(normalized_level, session.log_level):
        return False

    params: JSONObject = {"level": normalized_level}
    if logger is not None:
        params["logger"] = logger
    if data is not None:
        params["data"] = data
    notification: JSONObject = {
        "jsonrpc": "2.0",
        "method": "notifications/message",
        "params": params,
    }
    return await send_notification(session, notification)
