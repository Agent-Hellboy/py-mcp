"""Resource handlers."""

from __future__ import annotations

from ...capabilities.registry import get_server_capabilities
from ...protocol.errors import MCPErrorCode
from ..types import DispatchContext, DispatchResult, make_result
from .listing import build_paginated_list_result
from .registry import rpc_method


@rpc_method("resources/list")
async def handle_resources_list(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("resources"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "resources not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    resources = ctx.registry_manager.get_resource_registry().list_payload()
    return await build_paginated_list_result(
        ctx,
        items=resources,
        result_key="resources",
        filter_method="filter_resources",
    )


@rpc_method("resources/templates/list")
async def handle_resources_templates_list(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("resources"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "resources not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    templates = ctx.registry_manager.get_resource_registry().list_template_payload()
    return await build_paginated_list_result(
        ctx,
        items=templates,
        result_key="resourceTemplates",
        filter_method="filter_resource_templates",
    )


@rpc_method("resources/read")
async def handle_resources_read(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("resources"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "resources not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params_value = ctx.data.get("params")
    uri_value = params_value.get("uri") if isinstance(params_value, dict) else None
    if not isinstance(uri_value, str) or not uri_value:
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.INVALID_PARAMS, "Invalid params: missing uri")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = await ctx.payloads().build_resource_read(ctx.rpc_id, uri_value)
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


async def _handle_resource_subscription(ctx: DispatchContext, *, unsubscribe: bool) -> DispatchResult:
    if not ctx.supports("resources"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "resources not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params_value = ctx.data.get("params")
    params = params_value if isinstance(params_value, dict) else {}

    uris: list[str] = []
    raw_uris = params.get("uris")
    if isinstance(raw_uris, list):
        uris.extend(uri for uri in raw_uris if isinstance(uri, str) and uri)
    raw_single_uri = params.get("uri")
    if isinstance(raw_single_uri, str) and raw_single_uri:
        uris.append(raw_single_uri)
    if uris:
        uris = list(dict.fromkeys(uris))

    resource_caps = get_server_capabilities(ctx.app).get_capabilities().get("resources")
    subscribe_supported = False
    if isinstance(resource_caps, dict):
        subscribe_value = resource_caps.get("subscribe")
        subscribe_supported = bool(subscribe_value) if isinstance(subscribe_value, bool) else False
    if not subscribe_supported:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.METHOD_NOT_FOUND,
            "resources/subscribe not supported",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    if not uris:
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.INVALID_PARAMS, "Missing resource uri")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    resource_registry = ctx.registry_manager.get_resource_registry()
    unknown = [uri for uri in uris if not resource_registry.has_uri(uri)]
    if unknown:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.RESOURCE_NOT_FOUND,
            f"Unknown resources: {', '.join(unknown)}",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    for uri in uris:
        if unsubscribe:
            ctx.session_manager.unsubscribe_resource(ctx.session_id, uri)
        else:
            ctx.session_manager.subscribe_resource(ctx.session_id, uri)

    # Per the MCP spec, resources/subscribe and resources/unsubscribe return an
    # empty result; subscription state is observable via resource update
    # notifications, not the response body.
    payload = ctx.payloads().success(ctx.rpc_id, {})
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("resources/subscribe")
async def handle_resources_subscribe(ctx: DispatchContext) -> DispatchResult:
    return await _handle_resource_subscription(ctx, unsubscribe=False)


@rpc_method("resources/unsubscribe")
async def handle_resources_unsubscribe(ctx: DispatchContext) -> DispatchResult:
    return await _handle_resource_subscription(ctx, unsubscribe=True)


__all__ = [
    "handle_resources_list",
    "handle_resources_read",
    "handle_resources_subscribe",
    "handle_resources_templates_list",
    "handle_resources_unsubscribe",
]
