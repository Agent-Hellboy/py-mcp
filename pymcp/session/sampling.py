"""Helpers for server-initiated sampling (LLM completion) requests.

Per the MCP spec, sampling is a *client* capability.  The server sends
``sampling/createMessage`` to the client, which performs the LLM call and
returns the result.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI

from ..util.async_timeout import await_with_timeout
from .queueing import get_session_outbound_queue
from .store import get_session_manager


JSONObject = dict[str, Any]


def _parse_timeout_env(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if parsed <= 0 else parsed


_DEFAULT_SAMPLING_TIMEOUT = _parse_timeout_env(os.getenv("MCP_SAMPLING_TIMEOUT_SECONDS"))


async def request_sampling(
    app: FastAPI,
    session_id: str,
    params: JSONObject,
    *,
    timeout_seconds: float | None = None,
) -> JSONObject:
    """Send ``sampling/createMessage`` to the client and return the result.

    *params* should contain at least ``messages`` and ``maxTokens``.
    If *params* includes ``tools``, the client must have declared the
    ``sampling.tools`` sub-capability.

    Returns the ``result`` portion of the JSON-RPC response from the
    client.
    """

    manager = get_session_manager(app)
    session = manager.get_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    if not session.client_capabilities.supports_sampling():
        raise ValueError("Client does not support sampling capability")

    if params.get("tools") and not session.client_capabilities.supports_sampling_tools():
        raise ValueError("Client does not support tool use in sampling")

    queue = get_session_outbound_queue(session)
    rpc_id = str(uuid4())
    payload: JSONObject = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "sampling/createMessage",
        "params": params,
    }

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[JSONObject] = loop.create_future()
    manager.register_pending_request(session_id, rpc_id, fut)
    await queue.put(json.dumps(payload))

    effective_timeout = _DEFAULT_SAMPLING_TIMEOUT if timeout_seconds is None else timeout_seconds
    if effective_timeout is not None and effective_timeout <= 0:
        effective_timeout = None

    try:
        if effective_timeout is None:
            response: JSONObject = await fut
        else:
            response = await await_with_timeout(fut, effective_timeout)
    except asyncio.TimeoutError:
        session.pending_requests.pop(rpc_id, None)
        raise
    except asyncio.CancelledError:
        session.pending_requests.pop(rpc_id, None)
        raise

    result = response.get("result")
    if isinstance(result, dict):
        return result

    error = response.get("error")
    if isinstance(error, dict):
        code = error.get("code", -1)
        msg = error.get("message", "Sampling request failed")
        raise RuntimeError(f"Sampling error [{code}]: {msg}")

    return {}


__all__ = ["request_sampling"]
