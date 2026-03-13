"""Tools handlers."""

from __future__ import annotations

import asyncio
import inspect

import anyio

from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONObject
from ...tasks.cancellation import CancellationToken, CancelledError
from ..context import AppContext, RequestContext, SessionContext
from ..handlers.registry import rpc_method
from ..payloads import normalize_tool_result
from ..types import DispatchContext, DispatchResult, make_result
from .execution import run_tool_as_task
from .invocation import ToolArgs, ToolInvocationError, prepare_tool_invocation


async def _handle_tools_call_task_augmented(
    ctx: DispatchContext,
    *,
    tool_name: str,
    args: JSONObject,
    task_params: JSONObject,
) -> DispatchResult:
    ttl_value = task_params.get("ttl")
    ttl: int | None = None
    if ttl_value is not None and not isinstance(ttl_value, (int, float)):
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: ttl must be a number",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    if ttl_value is not None:
        ttl = int(ttl_value)

    meta = ctx.data.get("_meta") or ctx.data.get("meta") or {}
    progress_token = None
    if isinstance(meta, dict):
        token = meta.get("progressToken")
        if isinstance(token, str) and token:
            progress_token = token

    task_record = await ctx.task_manager.create_task(
        ctx.session_id,
        principal=ctx.session.principal,
        ttl=ttl,
        progress_token=progress_token,
    )
    task_token_id = ctx.cancellation_manager.create_token(request_id=f"task:{task_record.task_id}")
    await ctx.task_manager.set_cancel_token(task_record.task_id, task_token_id)
    task_cancel_token = CancellationToken(task_token_id, ctx.cancellation_manager)

    asyncio.create_task(
        run_tool_as_task(
            task_manager=ctx.task_manager,
            session=ctx.session,
            app=ctx.app,
            task_id=task_record.task_id,
            tool_name=tool_name,
            args=args,
            cancel_token=task_cancel_token,
            cancellation_manager=ctx.cancellation_manager,
        )
    )

    payload = ctx.payloads().success(ctx.rpc_id, {"task": task_record.to_wire()})
    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("tools/list")
async def handle_tools_list(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("tools"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "tools not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    payload = ctx.payloads().build_tools_list(ctx.rpc_id)
    authorizer = getattr(getattr(ctx.app, "state", None), "authorizer", None)
    principal = getattr(ctx.session, "principal", None)
    if authorizer and isinstance(payload, dict):
        result_value = payload.get("result")
        if isinstance(result_value, dict):
            tools_value = result_value.get("tools")
            if isinstance(tools_value, list):
                try:
                    tools = [entry for entry in tools_value if isinstance(entry, dict)]
                    result_value["tools"] = authorizer.filter_tools(principal, tools)
                except Exception:
                    pass

    await ctx.maybe_enqueue(payload)
    return make_result(200, json_response=True, payload=payload)


@rpc_method("tools/call")
async def handle_tools_call(ctx: DispatchContext) -> DispatchResult:
    if not ctx.supports("tools"):
        payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.METHOD_NOT_FOUND, "tools not supported")
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    params_value = ctx.data.get("params")
    params: JSONObject = params_value if isinstance(params_value, dict) else {}

    tool_name_value = params.get("name")
    if not isinstance(tool_name_value, str) or not tool_name_value:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INVALID_PARAMS,
            "Invalid params: missing tool name",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)
    tool_name = tool_name_value

    args_value = params.get("arguments")
    args: JSONObject = args_value if isinstance(args_value, dict) else {}
    task_params = params.get("task")
    if task_params is None and isinstance(args, dict):
        task_params = args.get("task")

    tool = ctx.registry_manager.get_tool_registry().get(tool_name)
    if tool is None:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.METHOD_NOT_FOUND,
            f"No such tool '{tool_name}'",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    task_support = None
    if isinstance(tool.execution, dict):
        task_support = tool.execution.get("taskSupport")

    task_request_supported = ctx.supports_task_request("tools", "call")
    if not task_request_supported:
        task_params = None

    if task_request_supported and task_support == "required" and not task_params:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.METHOD_NOT_FOUND,
            f"Tool '{tool_name}' requires task augmentation",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    if task_request_supported and (task_support in (None, "forbidden")) and task_params:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.METHOD_NOT_FOUND,
            f"Tool '{tool_name}' does not support task augmentation",
        )
        await ctx.maybe_enqueue(payload)
        return make_result(200, json_response=True, payload=payload)

    if task_request_supported and task_params:
        if not isinstance(task_params, dict):
            payload = ctx.payloads().error(ctx.rpc_id, MCPErrorCode.INVALID_PARAMS, "Invalid task params")
            await ctx.maybe_enqueue(payload)
            return make_result(200, json_response=True, payload=payload)
        return await _handle_tools_call_task_augmented(
            ctx,
            tool_name=tool_name,
            args=args,
            task_params=task_params,
        )

    token = ctx.cancellation_manager.create_token(request_id=ctx.rpc_id)
    cancel_token = CancellationToken(token, ctx.cancellation_manager)

    try:
        request_context = RequestContext(
            app_context=AppContext(ctx.app),
            session_context=SessionContext(
                ctx.session_id,
                capabilities=ctx.session.capabilities,
                user=ctx.session.principal,
            ),
            task_context=None,
        )
        tool_func, tool_args = prepare_tool_invocation(
            tool_info=tool,
            args=args,
            cancel_token=cancel_token,
            task_context=None,
            request_context=request_context,
        )

        async def _run_sync_with_cancellation(func, kwargs: ToolArgs, cancel_tok: CancellationToken | None) -> object:
            async def _run() -> object:
                def run_sync() -> object:
                    return func(**kwargs)

                return await anyio.to_thread.run_sync(run_sync)

            async def _wait_cancel() -> bool:
                assert cancel_tok is not None
                return await cancel_tok.wait()

            if cancel_tok is None:
                return await _run()

            run_task = asyncio.create_task(_run())
            cancel_task = asyncio.create_task(_wait_cancel())
            done, _ = await asyncio.wait({run_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
            if run_task in done:
                cancel_task.cancel()
                return await run_task
            cancelled = False
            try:
                cancelled = bool(cancel_task.result())
            except asyncio.CancelledError:
                cancelled = False
            if cancelled:
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                raise CancelledError()
            return await run_task

        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**tool_args)
        else:
            result = await _run_sync_with_cancellation(tool_func, tool_args, cancel_token)
            if inspect.iscoroutine(result):
                result = await result

        if ctx.cancellation_manager.is_cancelled(token):
            ctx.cancellation_manager.clear(token)
            return make_result(204, json_response=False, payload=None)

        payload = ctx.payloads().success(
            ctx.rpc_id,
            normalize_tool_result(result),
        )

        await ctx.maybe_enqueue(payload)
        ctx.cancellation_manager.clear(token)
        return make_result(200, json_response=True, payload=payload)
    except CancelledError:
        ctx.cancellation_manager.clear(token)
        return make_result(204, json_response=False, payload=None)
    except ToolInvocationError as exc:
        payload = ctx.payloads().error(ctx.rpc_id, exc.code, exc.message)
        await ctx.maybe_enqueue(payload)
        ctx.cancellation_manager.clear(token)
        return make_result(200, json_response=True, payload=payload)
    except Exception as exc:
        payload = ctx.payloads().error(
            ctx.rpc_id,
            MCPErrorCode.INTERNAL_ERROR,
            f"Error executing tool '{tool_name}': {exc}",
        )
        await ctx.maybe_enqueue(payload)
        ctx.cancellation_manager.clear(token)
        return make_result(200, json_response=True, payload=payload)


__all__ = ["handle_tools_call", "handle_tools_list"]
