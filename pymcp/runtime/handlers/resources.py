"""Resource handlers."""

from __future__ import annotations

import inspect
import logging

from ..helpers import ensure_mapping, maybe_await
from ..payloads import INTERNAL_ERROR, INVALID_PARAMS, METHOD_NOT_FOUND, error_response, normalize_resource_result, success
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


def _resource_call_kwargs(resource) -> dict[str, str]:
    signature = inspect.signature(resource.function)
    if "uri" in signature.parameters:
        return {"uri": resource.uri}
    return {}


@rpc_method("resources/list")
async def handle_resources_list(ctx: DispatchContext) -> DispatchResult:
    payload = success(
        ctx.rpc_id,
        {"resources": ctx.registry_manager.resource_registry.list_payload()},
    )
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("resources/read")
async def handle_resources_read(ctx: DispatchContext) -> DispatchResult:
    params = ensure_mapping(ctx.data.get("params"))
    uri = params.get("uri")
    if not isinstance(uri, str) or not uri:
        payload = error_response(ctx.rpc_id, INVALID_PARAMS, "Invalid params: missing uri")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    resource = ctx.registry_manager.resource_registry.get(uri)
    if resource is None:
        payload = error_response(ctx.rpc_id, METHOD_NOT_FOUND, f"No such resource '{uri}'")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    logger = logging.getLogger(__name__)
    try:
        result = await maybe_await(resource.function(**_resource_call_kwargs(resource)))
    except TypeError as exc:
        payload = error_response(ctx.rpc_id, INVALID_PARAMS, f"Invalid resource arguments: {exc}")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    except Exception as exc:
        logger.exception("Error reading resource '%s'", uri)
        payload = error_response(ctx.rpc_id, INTERNAL_ERROR, "Error reading resource")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = success(ctx.rpc_id, normalize_resource_result(uri, resource.mime_type, result))
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)
