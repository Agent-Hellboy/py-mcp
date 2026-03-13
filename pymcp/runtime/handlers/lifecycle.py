"""Lifecycle handlers."""

from __future__ import annotations

import asyncio
from typing import cast

from pydantic import ValidationError

from ...capabilities.registry import get_server_capabilities
from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONObject
from ...protocol.payload import negotiate_protocol_version
from ...protocol.types import ElicitationCreateParams
from ...protocol.validate import validate_against_schema
from ...protocol.validation_errors import format_pydantic_validation_error
from ...session.elicitation import request_elicitation
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("initialize")
async def handle_initialize(ctx: DispatchContext) -> DispatchResult:
    params_value = ctx.data.get("params")
    params = params_value if isinstance(params_value, dict) else {}

    requested_version_value = params.get("protocolVersion")
    requested_version = requested_version_value if isinstance(requested_version_value, str) else None
    accepted_version, version_error = negotiate_protocol_version(requested_version, ctx.server_settings)
    if version_error:
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.INVALID_PARAMS, version_error)
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    client_capabilities_value = params.get("capabilities")
    client_capabilities = client_capabilities_value if isinstance(client_capabilities_value, dict) else None
    client_info_value = params.get("clientInfo")
    client_info = client_info_value if isinstance(client_info_value, dict) else {}

    payload = ctx.payloads(protocol_version=accepted_version).build_initialize(ctx.rpc_id, client_capabilities)
    result_value = payload.get("result")
    result = result_value if isinstance(result_value, dict) else None
    capabilities_value = result.get("capabilities") if result is not None else None
    capabilities = capabilities_value if isinstance(capabilities_value, dict) else None

    authorizer = getattr(getattr(ctx.app, "state", None), "authorizer", None)
    principal = ctx.session.principal
    if authorizer and capabilities is not None:
        try:
            filtered = authorizer.filter_capabilities(principal, capabilities)
            if isinstance(filtered, dict):
                capabilities = filtered
                if result is not None:
                    result["capabilities"] = capabilities
        except Exception:
            pass

    ctx.session.client_capabilities = dict(client_capabilities or {})
    ctx.session.client_info = dict(client_info)
    ctx.session.capabilities = capabilities
    ctx.session.protocol_version = accepted_version

    await ctx.maybe_enqueue(payload)
    await ctx.session_manager.mark_initialize_started(ctx.session_id)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("notifications/initialized")
async def handle_notifications_initialized(ctx: DispatchContext) -> DispatchResult:
    await ctx.session_manager.mark_initialized(ctx.session_id)
    return make_result(202, json_response=False, payload=None)


@rpc_method("notifications/cancelled")
async def handle_notifications_cancelled(ctx: DispatchContext) -> DispatchResult:
    params = ctx.data.get("params", {}) or {}
    params_dict = params if isinstance(params, dict) else {}

    raw_request_id = params_dict.get("requestId")
    request_id: str | None = None
    if isinstance(raw_request_id, (str, int)) and not isinstance(raw_request_id, bool):
        request_id = str(raw_request_id) or None

    raw_reason = params_dict.get("reason")
    reason = str(raw_reason) if isinstance(raw_reason, (str, int, float)) and str(raw_reason) else None

    if request_id:
        if request_id.startswith("task:"):
            return make_result(202, json_response=False, payload=None)
        ctx.cancellation_manager.cancel(request_id, reason=reason)
    return make_result(202, json_response=False, payload=None)


@rpc_method("elicitation/create")
async def handle_elicitation_create(ctx: DispatchContext) -> DispatchResult:
    params_value = ctx.data.get("params")
    params = params_value if isinstance(params_value, dict) else {}
    try:
        elicitation_params = ElicitationCreateParams.model_validate(params)
    except ValidationError as exc:
        message, data = format_pydantic_validation_error(exc, loc_prefix="params")
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            message,
            data=data,
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    mode = elicitation_params.mode or "form"
    caps_value = get_server_capabilities(ctx.app).get_capabilities().get("elicitation")
    supported_modes = caps_value if isinstance(caps_value, dict) else {}
    if mode not in supported_modes:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.METHOD_NOT_FOUND,
            f"Elicitation mode '{mode}' not supported",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    if mode != "form":
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.METHOD_NOT_FOUND,
            f"Elicitation mode '{mode}' not supported server-side",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    task_id = None
    meta = ctx.data.get("_meta") or ctx.data.get("meta") or {}
    if isinstance(meta, dict):
        related = meta.get("io.modelcontextprotocol/related-task")
        if isinstance(related, dict):
            task_id_value = related.get("taskId")
            if isinstance(task_id_value, str):
                task_id = task_id_value

    try:
        _, elicited = await request_elicitation(
            ctx.app,
            ctx.session_id,
            params=cast(JSONObject, elicitation_params.model_dump(exclude_none=True)),
            task_id=task_id,
        )
    except asyncio.TimeoutError:
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.TIMEOUT, "Elicitation request timed out")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    except Exception as exc:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INTERNAL_ERROR,
            f"Error handling elicitation: {exc}",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    action = "accept"
    content = None
    if isinstance(elicited, dict):
        action = str(elicited.get("action", action))
        content = elicited.get("content")
    else:
        content = elicited

    if action not in {"accept", "decline", "cancel"}:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            f"Elicitation action '{action}' is not supported",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    if elicitation_params.requestedSchema and action == "accept":
        if not isinstance(content, dict):
            payload = ctx.payloads().error(
                ctx.rpc_id,
                MCPErrorCode.INVALID_PARAMS,
                "Elicitation response content must be an object for validation",
            )
            await ctx.maybe_enqueue(payload)
            return make_result(200, json_response=True, payload=payload)
        ok, message = validate_against_schema(content, elicitation_params.requestedSchema)
        if not ok:
            payload = ctx.payloads().error(
                ctx.rpc_id,
                MCPErrorCode.INVALID_PARAMS,
                f"Elicitation response failed validation: {message}",
            )
            await ctx.maybe_enqueue(payload)
            return make_result(200, json_response=True, payload=payload)

    result_payload: JSONObject = {"action": action}
    if content is not None:
        result_payload["content"] = content

    payload = ctx.payloads().success(ctx.rpc_id, result_payload)
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("ping")
async def handle_ping(ctx: DispatchContext) -> DispatchResult:
    payload = ctx.payloads().success(ctx.rpc_id, {})
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


__all__ = [
    "handle_elicitation_create",
    "handle_initialize",
    "handle_notifications_cancelled",
    "handle_notifications_initialized",
    "handle_ping",
]
