"""Helpers for formatting Pydantic validation errors for JSON-RPC responses."""

from __future__ import annotations

from pydantic import ValidationError

from .json_types import JSONObject, JSONValue


def _loc_to_path(loc: object, *, prefix: str | None) -> str:
    path = prefix or ""
    parts: list[object] = []
    if loc is None:
        parts = []
    elif isinstance(loc, (tuple, list)):
        parts = list(loc)
    else:
        parts = [loc]

    for part in parts:
        if isinstance(part, int):
            path = f"{path}[{part}]" if path else f"[{part}]"
        else:
            segment = str(part)
            path = f"{path}.{segment}" if path else segment
    return path


def format_pydantic_validation_error(
    exc: ValidationError,
    *,
    loc_prefix: str | None = "params",
) -> tuple[str, JSONObject]:
    raw_errors = exc.errors()
    errors: list[JSONValue] = []

    for raw in raw_errors:
        if not isinstance(raw, dict):
            continue
        path = _loc_to_path(raw.get("loc"), prefix=loc_prefix)
        msg = raw.get("msg")
        error_type = raw.get("type")
        errors.append(
            {
                "path": path,
                "message": msg if isinstance(msg, str) else str(msg),
                "type": error_type if isinstance(error_type, str) else str(error_type),
            }
        )

    data: JSONObject = {
        "validation": "pydantic",
        "error_count": len(errors),
        "errors": errors,
    }

    if not errors:
        return "Invalid params: validation failed", data

    first = errors[0]
    details = ""
    if isinstance(first, dict):
        first_path = first.get("path")
        first_message = first.get("message")
        if isinstance(first_path, str) and first_path and isinstance(first_message, str) and first_message:
            details = f"{first_path}: {first_message}"
        elif isinstance(first_message, str) and first_message:
            details = first_message
        elif isinstance(first_path, str) and first_path:
            details = first_path

    message = f"Invalid params: {details}" if details else "Invalid params: validation failed"
    if len(errors) > 1:
        message = f"{message} (and {len(errors) - 1} more)"

    return message, data


__all__ = ["format_pydantic_validation_error"]
