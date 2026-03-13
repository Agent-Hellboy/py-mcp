"""Helpers for server-initiated elicitation requests."""

from __future__ import annotations

import asyncio
import os
import json
from uuid import uuid4

from fastapi import FastAPI

from .queueing import get_session_outbound_queue
from .store import get_session_manager


JSONObject = dict[str, object]


def _parse_timeout_env(value: str | None) -> float | None:
    """Parse an elicitation timeout env var; non-positive values disable timeout."""

    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if parsed <= 0 else parsed


_DEFAULT_ELICITATION_TIMEOUT = _parse_timeout_env(os.getenv("MCP_ELICITATION_TIMEOUT_SECONDS"))


async def request_elicitation(
    app: FastAPI,
    session_id: str,
    params: JSONObject,
    *,
    task_id: str | None = None,
    timeout_seconds: float | None = None,
) -> tuple[str, JSONObject]:
    """Send `elicitation/create` to the client and wait for its response."""

    manager = get_session_manager(app)
    session = manager.get_session(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    params = dict(params or {})
    raw_mode = params.get("mode")
    mode = raw_mode if isinstance(raw_mode, str) and raw_mode else "form"
    params["mode"] = mode
    if mode != "form":
        raise ValueError(f"Elicitation mode '{mode}' not supported")

    raw_message = params.get("message")
    message = (
        raw_message
        if isinstance(raw_message, str) and raw_message
        else "Please provide the requested information."
    )
    params["message"] = message

    queue = get_session_outbound_queue(session)
    rpc_id = str(uuid4())
    payload: JSONObject = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "elicitation/create",
        "params": params,
    }
    if task_id:
        payload["_meta"] = {"io.modelcontextprotocol/related-task": {"taskId": task_id}}

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[JSONObject] = loop.create_future()
    manager.register_elicitation_future(session_id, rpc_id, fut)
    await queue.put(json.dumps(payload))

    effective_timeout = _DEFAULT_ELICITATION_TIMEOUT if timeout_seconds is None else timeout_seconds
    if effective_timeout is not None and effective_timeout <= 0:
        effective_timeout = None

    try:
        if effective_timeout is None:
            response: JSONObject = await fut
        else:
            async with asyncio.timeout(effective_timeout):
                response = await fut
    except asyncio.TimeoutError:
        session.pending_elicitations.pop(rpc_id, None)
        raise
    except asyncio.CancelledError:
        session.pending_elicitations.pop(rpc_id, None)
        raise

    return rpc_id, response
