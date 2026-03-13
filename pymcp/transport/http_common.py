"""Shared HTTP transport helpers."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request


def accept_contains(request: Request, content_type: str) -> bool:
    """Return True if the request Accept header allows the given content type."""
    wanted = content_type.lower().split(";")[0].strip()
    for part in request.headers.get("accept", "*/*").split(","):
        media_range, *params = [item.strip().lower() for item in part.split(";")]
        q = 1.0
        for param in params:
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
                break
        if q == 0:
            continue
        if media_range in {"*/*", wanted}:
            return True
        if media_range.endswith("/*") and wanted.startswith(media_range[:-1]):
            return True
    return False


def get_mcp_session_id(request: Request) -> str | None:
    return request.headers.get("MCP-Session-Id")


async def try_parse_json_body(request: Request) -> dict[str, Any] | list[Any] | None:
    try:
        payload = await request.json()
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if isinstance(payload, (dict, list)):
        return payload
    return None


__all__ = ["accept_contains", "get_mcp_session_id", "try_parse_json_body"]
