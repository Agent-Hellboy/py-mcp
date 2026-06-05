"""Logging handlers."""

from __future__ import annotations

from ...protocol.errors import MCPErrorCode
from ...protocol.logging_levels import normalize_log_level
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("logging/setLevel")
async def handle_logging_set_level(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("logging"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "logging not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params_value = ctx.data.get("params")
    params = params_value if isinstance(params_value, dict) else {}
    raw_level = params.get("level")
    if not isinstance(raw_level, str) or not raw_level.strip():
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: missing level",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    level = normalize_log_level(raw_level)
    if level is None:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            f"Invalid params: unknown log level '{raw_level}'",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    ctx.session.log_level = level
    payload = ctx.payloads().success(ctx.rpc_id, {})
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


__all__ = ["handle_logging_set_level"]
