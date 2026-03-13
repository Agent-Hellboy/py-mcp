"""JSON-RPC payload helpers."""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

from ..registries.registry import dump_value


JSONRPC_VERSION = "2.0"
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SESSION_NOT_FOUND = -32001
FORBIDDEN = -32003


def success(rpc_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": rpc_id, "result": result}


def error_response(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": rpc_id,
        "error": {"code": code, "message": message},
    }


def _coerce_tool_result_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, Mapping):
        return dict(value)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped

    as_dict = getattr(value, "dict", None)
    if callable(as_dict):
        dumped = as_dict()
        if isinstance(dumped, dict):
            return dumped

    return None


def normalize_tool_result(value: Any) -> dict[str, Any]:
    mapping_value = _coerce_tool_result_mapping(value)
    if mapping_value is not None and (
        "content" in mapping_value or "structuredContent" in mapping_value or "isError" in mapping_value
    ):
        return mapping_value
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
    "FORBIDDEN",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "JSONRPC_VERSION",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "SESSION_NOT_FOUND",
    "error_response",
    "normalize_prompt_result",
    "normalize_resource_result",
    "normalize_tool_result",
    "success",
]
