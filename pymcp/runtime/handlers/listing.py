"""Shared helpers for paginated MCP list handlers."""

from __future__ import annotations

from ...observability.logging import get_logger
from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONObject
from ...settings import ServerSettings
from ...util.pagination import paginate_list
from ..types import DispatchContext, DispatchResult, make_result


logger = get_logger(__name__)
_INVALID_CURSOR = object()


def list_page_size(app) -> int:
    settings = app.state.server_settings if hasattr(app.state, "server_settings") else ServerSettings()
    page_size = settings.capabilities.list_page_size
    return page_size if page_size > 0 else 50


def parse_list_cursor(ctx: DispatchContext) -> object | None:
    params = ctx.data.get("params")
    params_dict = params if isinstance(params, dict) else {}
    if "cursor" not in params_dict:
        return None
    raw_cursor = params_dict.get("cursor")
    return _INVALID_CURSOR if raw_cursor is None else raw_cursor


async def build_paginated_list_result(
    ctx: DispatchContext,
    *,
    items: list[JSONObject],
    result_key: str,
    filter_method: str | None = None,
) -> DispatchResult:
    authorizer = getattr(getattr(ctx.app, "state", None), "authorizer", None)
    principal = getattr(ctx.session, "principal", None)
    if authorizer and filter_method:
        filter_fn = getattr(authorizer, filter_method, None)
        if callable(filter_fn):
            try:
                items = list(filter_fn(principal, items))
            except Exception:
                logger.exception("Authorizer %s failed in %s", type(authorizer).__name__, filter_method)
                items = []

    page, next_cursor, cursor_error = paginate_list(items, parse_list_cursor(ctx), page_size=list_page_size(ctx.app))
    if cursor_error:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: invalid cursor",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    result: JSONObject = {result_key: page}
    if next_cursor:
        result["nextCursor"] = next_cursor
    payload = ctx.payloads().success(ctx.rpc_id, result)
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


__all__ = ["build_paginated_list_result", "list_page_size", "parse_list_cursor"]
