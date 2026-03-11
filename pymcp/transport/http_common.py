"""Shared HTTP transport helpers."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request


def accept_contains(request: Request, content_type: str) -> bool:
    accept = request.headers.get("accept", "*/*").lower()
    return accept == "*/*" or content_type.lower() in accept


def get_mcp_session_id(request: Request) -> str | None:
    return request.headers.get("MCP-Session-Id")


async def try_parse_json_body(request: Request) -> dict[str, Any] | list[Any] | None:
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError):
        return None
    if isinstance(payload, (dict, list)):
        return payload
    return None


__all__ = ["accept_contains", "get_mcp_session_id", "try_parse_json_body"]
