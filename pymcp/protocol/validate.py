"""Validation helpers for JSON-RPC envelopes and tool arguments."""

from __future__ import annotations

from collections.abc import Mapping
try:
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:  # pragma: no cover - exercised when optional dependency is absent
    Draft202012Validator = None

    class ValidationError(Exception):
        """Fallback validation error when jsonschema is unavailable."""

from .json_types import JSONObject, JSONValue


def validate_against_schema(instance: JSONObject, schema: JSONObject) -> tuple[bool, str]:
    if Draft202012Validator is None:
        return _fallback_validate_against_schema(instance, schema)
    try:
        Draft202012Validator(schema).validate(instance)
        return True, ""
    except ValidationError as exc:  # pragma: no cover - exercised via callers
        return False, exc.message


def _fallback_validate_against_schema(instance: JSONObject, schema: JSONObject) -> tuple[bool, str]:
    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if isinstance(key, str) and key not in instance:
                return False, f"'{key}' is a required property"

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for key, value in instance.items():
            prop_schema = properties.get(key)
            if not isinstance(prop_schema, dict):
                continue
            expected_type = prop_schema.get("type")
            if expected_type == "string" and not isinstance(value, str):
                return False, f"'{key}' must be a string"
            if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                return False, f"'{key}' must be an integer"
            if expected_type == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                return False, f"'{key}' must be a number"
            if expected_type == "boolean" and not isinstance(value, bool):
                return False, f"'{key}' must be a boolean"
            if expected_type == "object" and not isinstance(value, dict):
                return False, f"'{key}' must be an object"
            if expected_type == "array" and not isinstance(value, list):
                return False, f"'{key}' must be an array"
    return True, ""


def _schema_for_tool(tool_info: object) -> JSONObject | None:
    if isinstance(tool_info, Mapping):
        schema = tool_info.get("inputSchema")
        return schema if isinstance(schema, dict) else None
    schema = getattr(tool_info, "input_schema", None)
    return schema if isinstance(schema, dict) else None


def validate_tool_arguments(tool_info: object, arguments: JSONObject | None) -> tuple[bool, str]:
    schema = _schema_for_tool(tool_info)
    if not schema:
        return True, ""
    return validate_against_schema(arguments or {}, schema)


def validate_jsonrpc_request(payload: JSONValue) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "Invalid request payload"
    if payload.get("jsonrpc") != "2.0":
        return False, "Invalid JSON-RPC version"
    if "method" not in payload or not isinstance(payload.get("method"), str):
        return False, "Missing or invalid method"
    if "id" not in payload:
        return False, "Request id is required"
    params = payload.get("params")
    if "params" in payload and not isinstance(params, (dict, list)):
        return False, "Params must be an object or array"
    rpc_id = payload.get("id")
    if rpc_id is None:
        return False, "Request id must not be null"
    if isinstance(rpc_id, bool) or not isinstance(rpc_id, (str, int)):
        return False, "Request id must be a string or integer"
    return True, ""


__all__ = [
    "validate_against_schema",
    "validate_jsonrpc_request",
    "validate_tool_arguments",
]
