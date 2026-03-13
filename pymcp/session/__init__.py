"""Session state and app-scoped session manager."""

from .events import EventLog
from .elicitation import request_elicitation
from .lifecycle import SessionLifecycle
from .notifications import (
    attach_prompt_list_changed_notifications,
    attach_resource_list_changed_notifications,
    attach_resource_updated_notifications,
    attach_tool_list_changed_notifications,
    enqueue_notification,
    send_notification,
)
from .queueing import get_session_outbound_queue, safe_queue_put
from .store import SessionManager, get_session_manager, get_session_store
from .types import Session, SessionEvent, SessionState

__all__ = [
    "EventLog",
    "Session",
    "SessionEvent",
    "SessionLifecycle",
    "SessionManager",
    "SessionState",
    "attach_prompt_list_changed_notifications",
    "attach_resource_list_changed_notifications",
    "attach_resource_updated_notifications",
    "attach_tool_list_changed_notifications",
    "enqueue_notification",
    "get_session_outbound_queue",
    "get_session_manager",
    "get_session_store",
    "request_elicitation",
    "safe_queue_put",
    "send_notification",
]
