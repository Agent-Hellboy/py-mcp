"""Roots handlers."""

from __future__ import annotations

from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("roots/list")
async def handle_roots_list(ctx: DispatchContext) -> DispatchResult:
    payload = ctx.payloads().build_roots_list(ctx.rpc_id)
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


__all__ = ["handle_roots_list"]
