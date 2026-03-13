"""Tool handlers."""

from __future__ import annotations

from ..helpers import ensure_mapping, maybe_await
from ..payloads import INTERNAL_ERROR, INVALID_PARAMS, METHOD_NOT_FOUND, error_response, normalize_tool_result, success
from ..types import DispatchContext, DispatchResult, make_result
from ..handlers.registry import rpc_method


@rpc_method("tools/list")
async def handle_tools_list(ctx: DispatchContext) -> DispatchResult:
    payload = success(
        ctx.rpc_id,
        {"tools": ctx.registry_manager.tool_registry.list_payload()},
    )
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("tools/call")
async def handle_tools_call(ctx: DispatchContext) -> DispatchResult:
    params = ensure_mapping(ctx.data.get("params"))
    tool_name = params.get("name")
    arguments = ensure_mapping(params.get("arguments"))
    if not isinstance(tool_name, str) or not tool_name:
        payload = error_response(ctx.rpc_id, INVALID_PARAMS, "Invalid params: missing tool name")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    tool = ctx.registry_manager.tool_registry.get(tool_name)
    if tool is None:
        payload = error_response(ctx.rpc_id, METHOD_NOT_FOUND, f"No such tool '{tool_name}'")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    try:
        result = await maybe_await(tool.function(**arguments))
    except TypeError as exc:
        payload = error_response(ctx.rpc_id, INVALID_PARAMS, f"Invalid tool arguments: {exc}")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    except Exception as exc:
        payload = error_response(ctx.rpc_id, INTERNAL_ERROR, f"Error executing tool '{tool_name}': {exc}")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = success(ctx.rpc_id, normalize_tool_result(result))
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)
