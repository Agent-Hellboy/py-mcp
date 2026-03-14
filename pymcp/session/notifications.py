"""Session notification helpers and registry listener attachment."""

from __future__ import annotations

import json

from fastapi import FastAPI

from ..capabilities.registry import get_server_capabilities
from ..registries.registry import get_registry_manager
from .store import get_session_manager
from .types import Session, SessionState


JSONObject = dict[str, object]


async def send_notification(session: Session | None, notification: JSONObject) -> bool:
    """Queue a notification for a ready session with an attached stream."""

    if session is None:
        return False
    if session.lifecycle_state != SessionState.READY or not session.stream_attached:
        return False
    await session.queue.put(json.dumps(notification))
    return True


def enqueue_notification(session: Session | None, notification: JSONObject) -> bool:
    """Queue a notification without blocking for a ready session with an attached stream."""

    if session is None:
        return False
    if session.lifecycle_state != SessionState.READY or not session.stream_attached:
        return False
    try:
        session.queue.put_nowait(json.dumps(notification))
    except Exception:
        return False
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
