"""JSON-RPC 2.0 envelope and message helpers."""

from __future__ import annotations

from typing import cast

from .errors import build_error_response
from .json_types import JSONValue, JSONObject, RPCId
from .types import JSONRPCResponse


def build_result_envelope(rpc_id: RPCId, result: JSONObject) -> JSONObject:
    return cast(JSONObject, JSONRPCResponse(id=rpc_id, result=result).model_dump(exclude_none=True))


def build_error_envelope(
    rpc_id: RPCId,
    code: int,
    message: str,
    data: JSONValue | None = None,
) -> JSONObject:
    return build_error_response(rpc_id, code, message, data=data)


def is_notification(payload: JSONObject) -> bool:
    return "id" not in payload


def validate_rpc_id(rpc_id: object) -> bool:
    if rpc_id is None:
        return True
    if isinstance(rpc_id, bool):
        return False
    if isinstance(rpc_id, (str, int)):
        return True
    if isinstance(rpc_id, float):
        return rpc_id.is_integer()
    return False


__all__ = [
    "build_error_envelope",
    "build_result_envelope",
    "is_notification",
    "validate_rpc_id",
]
