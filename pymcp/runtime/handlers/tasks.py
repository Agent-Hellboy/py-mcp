"""Task handlers."""

from __future__ import annotations

from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONObject, JSONValue
from ...session.notifications import send_notification
from ...tasks.engine import TaskStatus
from ..types import DispatchContext, DispatchResult, make_result
from .registry import rpc_method


@rpc_method("tasks/get")
async def handle_tasks_get(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("tasks"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "tasks not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params = ctx.data.get("params")
    params_dict = params if isinstance(params, dict) else {}
    raw_task_id = params_dict.get("taskId")
    task_id = raw_task_id if isinstance(raw_task_id, str) and raw_task_id else None
    if task_id is None:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: missing taskId",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    record = await ctx.task_manager.get_task(task_id, ctx.session_id, principal=ctx.session.principal)
    if not record:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Failed to retrieve task: Task not found",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = ctx.payloads().success(ctx.rpc_id, record.to_wire())
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("tasks/list")
async def handle_tasks_list(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("tasks"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "tasks not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params = ctx.data.get("params")
    params_dict = params if isinstance(params, dict) else {}
    raw_cursor = params_dict.get("cursor")
    cursor = raw_cursor if isinstance(raw_cursor, str) and raw_cursor else None
    tasks, next_cursor, cursor_error = await ctx.task_manager.list_tasks(
        ctx.session_id,
        cursor,
        principal=ctx.session.principal,
    )
    if cursor_error:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: invalid cursor",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    result: JSONObject = {"tasks": [task.to_wire() for task in tasks]}
    if next_cursor:
        result["nextCursor"] = next_cursor
    payload = ctx.payloads().success(ctx.rpc_id, result)
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("tasks/cancel")
async def handle_tasks_cancel(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("tasks"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "tasks not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params = ctx.data.get("params")
    params_dict = params if isinstance(params, dict) else {}
    raw_task_id = params_dict.get("taskId")
    task_id = raw_task_id if isinstance(raw_task_id, str) and raw_task_id else None
    if task_id is None:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: missing taskId",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    record = await ctx.task_manager.get_task(task_id, ctx.session_id, principal=ctx.session.principal)
    if not record:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Failed to retrieve task: Task not found",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    if record.is_terminal():
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            f"Cannot cancel task: already in terminal status '{record.status.value}'",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    if record.cancel_token_id:
        ctx.cancellation_manager.cancel(record.cancel_token_id)

    await ctx.task_manager.cancel_task_handle(task_id)
    prev_last_updated = record.last_updated_at
    record = await ctx.task_manager.mark_task_cancelled(
        task_id,
        ctx.session_id,
        principal=ctx.session.principal,
    )
    if not record:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Failed to cancel task: Task not found",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    if record.last_updated_at == prev_last_updated:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            f"Cannot cancel task: already in terminal status '{record.status.value}'",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    await send_notification(
        ctx.session,
        {
            "jsonrpc": "2.0",
            "method": "notifications/tasks/status",
            "params": record.to_wire(),
        },
    )

    payload = ctx.payloads().success(ctx.rpc_id, record.to_wire())
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("tasks/result")
async def handle_tasks_result(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("tasks"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "tasks not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params = ctx.data.get("params")
    params_dict = params if isinstance(params, dict) else {}
    raw_task_id = params_dict.get("taskId")
    task_id = raw_task_id if isinstance(raw_task_id, str) and raw_task_id else None
    if task_id is None:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: missing taskId",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    record = await ctx.task_manager.get_task(task_id, ctx.session_id, principal=ctx.session.principal)
    if not record:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Failed to retrieve task: Task not found",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    meta: JSONObject = {"io.modelcontextprotocol/related-task": {"taskId": task_id}}
    if not record.is_terminal():
        await record.completion_event.wait()
        record = await ctx.task_manager.get_task(task_id, ctx.session_id, principal=ctx.session.principal)
        if not record:
            payload = ctx.payloads().error(
                ctx.rpc_id,
                MCPErrorCode.INVALID_PARAMS,
                "Failed to retrieve task: Task has expired",
            )
            await ctx.maybe_enqueue(payload)
            return make_result(200, json_response=True, payload=payload)

    if record.error:
        err_obj: JSONObject = record.error if isinstance(record.error, dict) else {}
        raw_code = err_obj.get("code")
        code = raw_code if isinstance(raw_code, int) and not isinstance(raw_code, bool) else MCPErrorCode.INTERNAL_ERROR
        raw_message = err_obj.get("message")
        message = raw_message if isinstance(raw_message, str) and raw_message else "Task failed"
        data: JSONValue | None = err_obj.get("data")
        response_payload = ctx.payloads().error_with_meta(
            ctx.rpc_id,
            code,
            message,
            data=data,
            meta=meta,
        )
    elif record.result:
        response_payload = ctx.payloads().success_with_meta(ctx.rpc_id, record.result, meta=meta)
    elif record.status == TaskStatus.CANCELLED:
        response_payload = ctx.payloads().error_with_meta(
            ctx.rpc_id,
            MCPErrorCode.INVALID_REQUEST,
            "Task was cancelled",
            meta=meta,
        )
    else:
        response_payload = ctx.payloads().error_with_meta(
            ctx.rpc_id,
            MCPErrorCode.INTERNAL_ERROR,
            "Task did not produce a result",
            meta=meta,
        )

    await ctx.maybe_enqueue(response_payload)
    return make_result(200, json_response=True, payload=response_payload)


__all__ = [
    "handle_tasks_cancel",
    "handle_tasks_get",
    "handle_tasks_list",
    "handle_tasks_result",
]
