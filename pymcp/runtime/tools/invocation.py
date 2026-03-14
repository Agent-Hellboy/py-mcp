"""Tool invocation helpers (argument validation + dependency injection)."""

from __future__ import annotations

import inspect

from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONValue, JSONObject
from ...protocol.validate import validate_tool_arguments
from ...registries.registry import ToolDefinition, ToolFunction
from ...tasks.cancellation import CancellationToken
from ...tasks.engine import TaskContext
from ..context import RequestContext


class ToolInvocationError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


ToolArgumentValue = JSONValue | CancellationToken | TaskContext | RequestContext
ToolArgs = dict[str, ToolArgumentValue]


def prepare_tool_invocation(
    *,
    tool_info: ToolDefinition,
    args: JSONObject | None,
    cancel_token: CancellationToken | None = None,
    task_context: TaskContext | None = None,
    request_context: RequestContext | None = None,
) -> tuple[ToolFunction, ToolArgs]:
    tool_func = tool_info.function
    signature = inspect.signature(tool_func)

    provided_args: JSONObject = args or {}
    tool_args: ToolArgs = {
        key: value
        for key, value in provided_args.items()
        if key not in ("cancel_token", "task_context", "request_context")
    }

    if "cancel_token" in signature.parameters and cancel_token is not None:
        tool_args["cancel_token"] = cancel_token
    if "task_context" in signature.parameters and task_context is not None:
        tool_args["task_context"] = task_context
    if "request_context" in signature.parameters and request_context is not None:
        tool_args["request_context"] = request_context

    validation_args: JSONObject = dict(provided_args)
    validation_args.pop("cancel_token", None)
    validation_args.pop("task_context", None)
    validation_args.pop("request_context", None)

    ok, err = validate_tool_arguments(tool_info, validation_args)
    if not ok:
        raise ToolInvocationError(MCPErrorCode.INVALID_PARAMS, f"Invalid params: {err}")

    return tool_func, tool_args


__all__ = ["ToolArgs", "ToolInvocationError", "prepare_tool_invocation"]
