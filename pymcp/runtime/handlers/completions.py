"""Completion handler for argument autocompletion.

Implements ``completion/complete`` which provides completion suggestions
for prompt or resource template arguments.
"""

from __future__ import annotations

from ...observability.logging import get_logger
from ...protocol.errors import MCPErrorCode
from ..types import DispatchContext, DispatchResult, make_result
from .completion_support import CompletionResolutionError, resolve_prompt_completion, resolve_resource_completion
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
    if not isinstance(arg_name, str) or not arg_name:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Missing or invalid argument name",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    if not isinstance(arg_value, str):
        arg_value = "" if arg_value is None else str(arg_value)

    context = params.get("context")
    if context is not None and not isinstance(context, dict):
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid completion context",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    _ = context

    try:
        if ref_type == "ref/prompt":
            prompt_name = ref.get("name", "")
            if not isinstance(prompt_name, str) or not prompt_name:
                raise CompletionResolutionError(MCPErrorCode.INVALID_PARAMS, "Missing prompt name")
            completion = resolve_prompt_completion(
                registry_manager=ctx.registry_manager,
                prompt_name=prompt_name,
                argument_name=arg_name,
                argument_value=arg_value,
            )
        elif ref_type == "ref/resource":
            uri_template = ref.get("uri", "")
            if not isinstance(uri_template, str) or not uri_template:
                raise CompletionResolutionError(MCPErrorCode.INVALID_PARAMS, "Missing resource URI template")
            completion = resolve_resource_completion(
                registry_manager=ctx.registry_manager,
                uri_template=uri_template,
                argument_name=arg_name,
                argument_value=arg_value,
            )
        else:
            payload = ctx.payloads().error(
                ctx.rpc_id,
                MCPErrorCode.INVALID_PARAMS,
                f"Unsupported completion ref type: {ref_type}",
            )
            await ctx.maybe_enqueue(payload)
            return make_result(200, json_response=True, payload=payload)
    except CompletionResolutionError as exc:
        payload = ctx.payloads().error(ctx.rpc_id, exc.code, exc.message)
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = ctx.payloads().success(ctx.rpc_id, {"completion": completion})
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


__all__ = ["handle_completion_complete"]
