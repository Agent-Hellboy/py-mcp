"""Completion handler for argument autocompletion.

Implements ``completion/complete`` which provides completion suggestions
for prompt or resource arguments.
"""

from __future__ import annotations

from ...observability.logging import get_logger
from ...protocol.errors import MCPErrorCode
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method

logger = get_logger(__name__)


@rpc_method("completion/complete")
async def handle_completion_complete(ctx: DispatchContext) -> DispatchResult:
    params_value = ctx.data.get("params")
    params = params_value if isinstance(params_value, dict) else {}

    ref = params.get("ref")
    if not isinstance(ref, dict):
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Missing or invalid 'ref' in completion request",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    argument = params.get("argument")
    if not isinstance(argument, dict):
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Missing or invalid 'argument' in completion request",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    ref_type = ref.get("type", "")
    arg_name = argument.get("name", "")
    arg_value = argument.get("value", "")

    values: list[str] = []

    if ref_type == "ref/prompt":
        prompt_name = ref.get("name", "")
        prompt_def = ctx.registry_manager.prompt_registry.get(prompt_name)
        if prompt_def is not None:
            for prompt_arg in prompt_def.arguments:
                if prompt_arg.get("name") == arg_name:
                    # Prompts don't carry enum values, so return empty
                    break
    elif ref_type == "ref/resource":
        pass  # Resource completions are not commonly used

    payload = ctx.payloads().success(
        ctx.rpc_id,
        {
            "completion": {
                "values": values,
                "hasMore": False,
            }
        },
    )
    _ = arg_value  # reserved for future filtering
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


__all__ = ["handle_completion_complete"]
