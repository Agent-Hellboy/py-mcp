"""Roots notification handlers.

Per the MCP spec, ``roots/list`` is a server-to-client request (the server
asks the client for its roots).  The client may send
``notifications/roots/list_changed`` to inform the server that its root
set has been updated.
"""

from __future__ import annotations

from ...observability.logging import get_logger
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method

logger = get_logger(__name__)


_roots_changed_callbacks: list[object] = []


def on_roots_changed(callback) -> None:
    """Register a callback to be invoked when the client sends
    ``notifications/roots/list_changed``.

    Callbacks receive ``(app, session_id)`` as arguments.
    """
    _roots_changed_callbacks.append(callback)


@rpc_method("notifications/roots/list_changed")
async def handle_roots_list_changed(ctx: DispatchContext) -> DispatchResult:
    """Handle the client notification that its root list changed."""
    logger.info("Client %s notified roots/list_changed", ctx.session_id)
    for cb in _roots_changed_callbacks:
        try:
            result = cb(ctx.app, ctx.session_id)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            logger.exception("Error in roots_changed callback")
    return make_result(202, json_response=False, payload=None)


__all__ = ["handle_roots_list_changed", "on_roots_changed"]
