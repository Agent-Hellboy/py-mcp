"""Helpers for server-initiated roots/list requests.

Per the MCP spec, roots are a *client* capability. The server sends
``roots/list`` to the client and the client responds with its available
roots.  Clients may also send ``notifications/roots/list_changed`` when
their root set changes.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from fastapi import FastAPI

from .queueing import get_session_outbound_queue
from .store import get_session_manager


JSONObject = dict[str, Any]


async def request_roots_list(
    app: FastAPI,
    session_id: str,
    *,
    timeout_seconds: float | None = 30.0,
) -> list[JSONObject]:
    """Send ``roots/list`` to the client and return the roots array.

    Raises ``ValueError`` if the client did not declare the ``roots``
    capability, or if the session cannot be found.
    """

    manager = get_session_manager(app)
    session = manager.get_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    if not session.client_capabilities.supports_roots():
        raise ValueError("Client does not support roots capability")

    queue = get_session_outbound_queue(session)
    rpc_id = str(uuid4())
    payload: JSONObject = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "roots/list",
    }

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[JSONObject] = loop.create_future()
    manager.register_pending_request(session_id, rpc_id, fut)
    await queue.put(json.dumps(payload))

    effective_timeout = timeout_seconds
    if effective_timeout is not None and effective_timeout <= 0:
        effective_timeout = None

    try:
        if effective_timeout is None:
            response: JSONObject = await fut
        else:
            async with asyncio.timeout(effective_timeout):
                response = await fut
    except asyncio.TimeoutError:
        session.pending_requests.pop(rpc_id, None)
        raise
    except asyncio.CancelledError:
        session.pending_requests.pop(rpc_id, None)
        raise

    result = response.get("result")
    if isinstance(result, dict):
        roots = result.get("roots")
        if isinstance(roots, list):
            return roots
    return []


__all__ = ["request_roots_list"]
