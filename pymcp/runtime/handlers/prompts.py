"""Prompt handlers."""

from __future__ import annotations

from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONObject
from ..types import DispatchContext, DispatchResult, make_result
from .listing import build_paginated_list_result
from .registry import rpc_method


@rpc_method("prompts/list")
async def handle_prompts_list(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("prompts"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "prompts not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    prompts = ctx.registry_manager.get_prompt_registry().list_payload()
    return await build_paginated_list_result(
        ctx,
        items=prompts,
        result_key="prompts",
        filter_method="filter_prompts",
    )


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
