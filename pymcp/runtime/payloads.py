"""JSON-RPC payload helpers."""

from __future__ import annotations

import base64
from typing import Any

from ..registries.registry import dump_value


JSONRPC_VERSION = "2.0"
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def success(rpc_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": rpc_id, "result": result}


def error_response(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }


def normalize_tool_result(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and (
        "content" in value or "structuredContent" in value or "isError" in value
    ):
        return value
    if isinstance(value, list):
        return {"content": value}
    return {"content": [{"type": "text", "text": dump_value(value)}]}


def normalize_prompt_result(description: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and "messages" in value:
        result = value.copy()
        result.setdefault("description", description)
        return result
    if isinstance(value, list):
        return {"description": description, "messages": value}
    return {
        "description": description,
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": dump_value(value)},
            }
        ],
    }


def normalize_resource_result(uri: str, mime_type: str, value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and "contents" in value:
        return value
    if isinstance(value, bytes):
        encoded = base64.b64encode(value).decode("ascii")
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": mime_type,
                    "blob": encoded,
                }
            ]
        }
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": mime_type,
                "text": dump_value(value),
            }
        ]
    }


__all__ = [
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "JSONRPC_VERSION",
    "METHOD_NOT_FOUND",
    "error_response",
    "normalize_prompt_result",
    "normalize_resource_result",
    "normalize_tool_result",
    "success",
]
