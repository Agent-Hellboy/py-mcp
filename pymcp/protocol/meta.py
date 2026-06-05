"""Helpers for JSON-RPC ``_meta`` validation and propagation."""

from __future__ import annotations

from .errors import MCPErrorCode
from .json_types import JSONValue, JSONObject


class MetaValidationError(ValueError):
    """Raised when request metadata is malformed."""

    code = MCPErrorCode.INVALID_PARAMS


def validate_meta_value(value: JSONValue | None, *, location: str) -> JSONObject:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MetaValidationError(f"{location} must be an object")
    return dict(value)


def validate_request_meta(data: JSONObject) -> None:
    if "_meta" in data:
        validate_meta_value(data.get("_meta"), location="_meta")
    params = data.get("params")
    if isinstance(params, dict) and "_meta" in params:
        validate_meta_value(params.get("_meta"), location="params._meta")


def extract_request_meta(data: JSONObject) -> JSONObject:
    merged: JSONObject = {}
    top_level = data.get("_meta")
    if isinstance(top_level, dict):
        merged.update(top_level)
    params = data.get("params")
    if isinstance(params, dict):
        params_meta = params.get("_meta")
        if isinstance(params_meta, dict):
            merged.update(params_meta)
    return merged


def attach_meta(payload: JSONObject, meta: JSONObject | None) -> JSONObject:
    if not meta:
        return payload
    merged = dict(payload)
    existing = merged.get("_meta")
    if isinstance(existing, dict):
        combined = dict(existing)
        combined.update(meta)
        merged["_meta"] = combined
    else:
        merged["_meta"] = dict(meta)
    return merged


def split_result_meta(result: JSONObject) -> tuple[JSONObject, JSONObject | None]:
    if "_meta" not in result:
        return result, None
    payload = dict(result)
    meta_value = payload.pop("_meta")
    if isinstance(meta_value, dict):
        return payload, meta_value
    return result, None


__all__ = [
    "MetaValidationError",
    "attach_meta",
    "extract_request_meta",
    "split_result_meta",
    "validate_meta_value",
    "validate_request_meta",
]
