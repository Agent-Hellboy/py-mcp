"""Session queue selection and non-blocking enqueue helpers."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from ..observability.logging import get_logger
from .types import Session


logger = get_logger(__name__)

_FOLLOW_UP_WINDOW_SECONDS = 60.0


def notification_method(notification: dict[str, Any]) -> str:
    method = notification.get("method")
    return method if isinstance(method, str) else "<unknown>"


def notification_detail(notification: dict[str, Any]) -> str | None:
    params = notification.get("params")
    if not isinstance(params, dict):
        return None
    uri = params.get("uri")
    if isinstance(uri, str):
        return uri
    return None


def expected_client_follow_up(method: str) -> str:
    return {
        "notifications/resources/updated": "resources/read or resources/list",
        "notifications/tools/list_changed": "tools/list",
        "notifications/prompts/list_changed": "prompts/list",
        "notifications/resources/list_changed": "resources/list",
        "notifications/message": "none (informational)",
        "notifications/progress": "none (informational)",
        "notifications/tasks/status": "tasks/get or tasks/result",
    }.get(method, "depends on client")


def record_outbound_notification(session: Session, notification: dict[str, Any]) -> None:
    method = notification_method(notification)
    detail = notification_detail(notification)
    session.last_outbound_notification_method = method
    session.last_outbound_notification_detail = detail
    session.last_outbound_notification_at = time.monotonic()
    logger.info(
        "[MCP] server -> client notification sent method=%s session=%s detail=%s expected_client_follow_up=%s",
        method,
        session.session_id,
        detail or "",
        expected_client_follow_up(method),
    )


def log_client_follow_up_request(session: Session, *, request_method: str) -> None:
    previous = session.last_outbound_notification_method
    previous_at = session.last_outbound_notification_at
    if not previous or previous_at is None:
        return
    elapsed_ms = int((time.monotonic() - previous_at) * 1000)
    if elapsed_ms > int(_FOLLOW_UP_WINDOW_SECONDS * 1000):
        return
    logger.info(
        "[HTTP][MCP] client follow-up request method=%s session=%s "
        "after_notification=%s notification_detail=%s elapsed_ms=%s",
        request_method,
        session.session_id,
        previous,
        session.last_outbound_notification_detail or "",
        elapsed_ms,
    )


def log_notification_sent(*, method: str, session_id: str) -> None:
    logger.info("[MCP] server -> client notification sent method=%s session=%s", method, session_id)


def log_notification_skipped(
    *,
    method: str,
    reason: str,
    session_id: str | None = None,
) -> None:
    if session_id is None:
        logger.debug(
            "[MCP] server -> client notification skipped method=%s reason=%s",
            method,
            reason,
        )
        return
    logger.debug(
        "[MCP] server -> client notification skipped method=%s session=%s reason=%s",
        method,
        session_id,
        reason,
    )


def get_session_outbound_queue(session: Session) -> asyncio.Queue[str]:
    """Return the outbound queue used for server-to-client messages."""

    return session.queue


def safe_queue_put(queue: asyncio.Queue[str] | None, msg: str) -> bool:
    """Put onto a queue without blocking; return False when backpressure wins."""

    if not queue:
        return False
    try:
        queue.put_nowait(msg)
    except (asyncio.QueueFull, RuntimeError):
        return False
    return True
