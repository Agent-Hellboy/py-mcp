"""Standardized error handling for MCP protocol payloads."""

from __future__ import annotations

from typing import cast

from .json_types import JSONValue, JSONObject, RPCId
from .types import JSONRPCError, JSONRPCResponse


class MCPErrorCode:
    """Standard MCP error codes."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    SESSION_NOT_FOUND = -32000
    SESSION_EXPIRED = -32001
    RESOURCE_NOT_FOUND = -32002
    TOOL_EXECUTION_FAILED = -32003
    CANCELLED = -32004
    TIMEOUT = -32005
    UNAUTHORIZED = -32006
    FORBIDDEN = -32007
    RATE_LIMITED = -32008
    URL_ELICITATION_REQUIRED = -32042


class MCPError(Exception):
    """MCP-specific protocol exception."""

    def __init__(self, code: int, message: str, data: JSONValue | None = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"[{code}] {message}")


def build_error_response(
    rpc_id: RPCId,
    code: int,
    message: str,
    data: JSONValue | None = None,
) -> JSONObject:
    error = JSONRPCError(code=code, message=message, data=data)
    response = JSONRPCResponse(id=rpc_id, error=error)
    return cast(JSONObject, response.model_dump(exclude_none=True))


def build_parse_error(rpc_id: RPCId) -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.PARSE_ERROR, "Parse error")


def build_invalid_request_error(rpc_id: RPCId, message: str = "Invalid Request") -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.INVALID_REQUEST, message)


def build_method_not_found_error(rpc_id: RPCId, method: str) -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.METHOD_NOT_FOUND, f"Method not found: {method}")


def build_invalid_params_error(rpc_id: RPCId, message: str) -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.INVALID_PARAMS, f"Invalid params: {message}")


def build_internal_error(
    rpc_id: RPCId,
    message: str = "Internal error",
    data: JSONValue | None = None,
) -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.INTERNAL_ERROR, message, data)


def build_session_not_found_error(rpc_id: RPCId) -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.SESSION_NOT_FOUND, "Session not found")


def build_resource_not_found_error(rpc_id: RPCId, uri: str) -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.RESOURCE_NOT_FOUND, f"Resource not found: {uri}")


def build_cancelled_error(rpc_id: RPCId) -> JSONObject:
    return build_error_response(rpc_id, MCPErrorCode.CANCELLED, "Request was cancelled")


__all__ = [
    "MCPError",
    "MCPErrorCode",
    "build_cancelled_error",
    "build_error_response",
    "build_internal_error",
    "build_invalid_params_error",
    "build_invalid_request_error",
    "build_method_not_found_error",
    "build_parse_error",
    "build_resource_not_found_error",
    "build_session_not_found_error",
]
