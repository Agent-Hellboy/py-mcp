"""Resource handlers."""

from __future__ import annotations

from ...capabilities.registry import get_server_capabilities
from ...protocol.errors import MCPErrorCode
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("resources/list")
async def handle_resources_list(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("resources"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "resources not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = ctx.payloads().build_resources_list(ctx.rpc_id)
    authorizer = getattr(getattr(ctx.app, "state", None), "authorizer", None)
    principal = getattr(ctx.session, "principal", None)
    if authorizer and isinstance(payload, dict):
        result_value = payload.get("result")
        if isinstance(result_value, dict):
            resources_value = result_value.get("resources")
            if isinstance(resources_value, list):
                try:
                    resources = [entry for entry in resources_value if isinstance(entry, dict)]
                    result_value["resources"] = authorizer.filter_resources(principal, resources)
                except Exception:
                    pass

    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


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
    unknown = [uri for uri in uris if resource_registry.get(uri) is None]
    if unknown:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.RESOURCE_NOT_FOUND,
            f"Unknown resources: {', '.join(unknown)}",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    subscribed: list[str] = []
    unsubscribed: list[str] = []
    for uri in uris:
        if unsubscribe:
            if ctx.session_manager.unsubscribe_resource(ctx.session_id, uri):
                unsubscribed.append(uri)
        else:
            if ctx.session_manager.subscribe_resource(ctx.session_id, uri):
                subscribed.append(uri)

    payload = ctx.payloads().success(
        ctx.rpc_id,
        {
            "subscribed": subscribed,
            "unsubscribed": unsubscribed,
        },
    )
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
    "handle_resources_unsubscribe",
]
