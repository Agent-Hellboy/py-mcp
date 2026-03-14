"""Prompt handlers."""

from __future__ import annotations

from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONObject
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("prompts/list")
async def handle_prompts_list(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("prompts"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "prompts not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = ctx.payloads().build_prompts_list(ctx.rpc_id)
    authorizer = getattr(getattr(ctx.app, "state", None), "authorizer", None)
    principal = getattr(ctx.session, "principal", None)
    if authorizer and isinstance(payload, dict):
        result_value = payload.get("result")
        if isinstance(result_value, dict):
            prompts_value = result_value.get("prompts")
            if isinstance(prompts_value, list):
                try:
                    prompts = [entry for entry in prompts_value if isinstance(entry, dict)]
                    filtered = authorizer.filter_prompts(principal, prompts)
                    result_value["prompts"] = [cast_entry for cast_entry in filtered]
                except Exception:
                    pass

    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("prompts/get")
async def handle_prompts_get(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("prompts"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "prompts not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params_value = ctx.data.get("params")
    params: JSONObject = params_value if isinstance(params_value, dict) else {}

    prompt_name_value = params.get("name")
    prompt_name = prompt_name_value if isinstance(prompt_name_value, str) else ""
    prompt_arguments_value = params.get("arguments")
    prompt_arguments: JSONObject = prompt_arguments_value if isinstance(prompt_arguments_value, dict) else {}

    payload = await ctx.payloads().build_prompts_get(ctx.rpc_id, prompt_name, prompt_arguments)
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


__all__ = ["handle_prompts_get", "handle_prompts_list"]
