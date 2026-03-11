"""Lifecycle handlers."""

from __future__ import annotations

from ...capabilities import build_capabilities
from ..helpers import ensure_mapping, select_protocol_version
from ..payloads import success
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("initialize")
async def handle_initialize(ctx: DispatchContext) -> DispatchResult:
    params = ensure_mapping(ctx.data.get("params"))
    session = ctx.session
    session.protocol_version = select_protocol_version(params.get("protocolVersion"), ctx.server_settings)
    session.client_capabilities = ensure_mapping(params.get("capabilities"))
    session.client_info = ensure_mapping(params.get("clientInfo"))
    await ctx.session_manager.mark_initialize_started(ctx.session_id)

    payload = success(
        ctx.rpc_id,
        {
            "protocolVersion": session.protocol_version,
            "capabilities": build_capabilities(
                ctx.server_settings.capabilities,
                ctx.registry_manager.tool_registry,
                ctx.registry_manager.prompt_registry,
                ctx.registry_manager.resource_registry,
            ),
            "serverInfo": {
                "name": ctx.server_settings.name,
                "version": ctx.server_settings.version,
            },
        },
    )
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("ping")
async def handle_ping(ctx: DispatchContext) -> DispatchResult:
    payload = success(ctx.rpc_id, {})
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("notifications/initialized")
async def handle_initialized_notification(ctx: DispatchContext) -> DispatchResult:
    await ctx.session_manager.mark_initialized(ctx.session_id)
    return make_result(202, json_response=False, payload=None)
