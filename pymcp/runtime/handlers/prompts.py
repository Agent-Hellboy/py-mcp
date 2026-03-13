"""Prompt handlers."""

from __future__ import annotations

import logging

from ..helpers import ensure_mapping, maybe_await
from ..payloads import INTERNAL_ERROR, INVALID_PARAMS, error_response, normalize_prompt_result, success
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("prompts/list")
async def handle_prompts_list(ctx: DispatchContext) -> DispatchResult:
    payload = success(
        ctx.rpc_id,
        {"prompts": ctx.registry_manager.prompt_registry.list_payload()},
    )
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("prompts/get")
async def handle_prompts_get(ctx: DispatchContext) -> DispatchResult:
    params = ensure_mapping(ctx.data.get("params"))
    prompt_name = params.get("name")
    arguments = ensure_mapping(params.get("arguments"))
    if not isinstance(prompt_name, str) or not prompt_name:
        payload = error_response(ctx.rpc_id, INVALID_PARAMS, "Invalid params: missing prompt name")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    prompt = ctx.registry_manager.prompt_registry.get(prompt_name)
    if prompt is None:
        payload = error_response(ctx.rpc_id, INVALID_PARAMS, f"No such prompt '{prompt_name}'")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    logger = logging.getLogger(__name__)
    try:
        result = await maybe_await(prompt.function(**arguments))
    except TypeError as exc:
        payload = error_response(ctx.rpc_id, INVALID_PARAMS, f"Invalid prompt arguments: {exc}")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    except Exception as exc:
        logger.exception("Unexpected error rendering prompt '%s'", prompt_name)
        payload = error_response(ctx.rpc_id, INTERNAL_ERROR, f"Error rendering prompt '{prompt_name}': {exc}")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = success(ctx.rpc_id, normalize_prompt_result(prompt.description, result))
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)
