"""Tool execution orchestration (runner selection + task finalization)."""

from __future__ import annotations

import asyncio
import inspect
from typing import Final, cast

from fastapi import FastAPI

from ...observability.logging import get_logger
from ...protocol.errors import MCPErrorCode
from ...protocol.json_types import JSONObject
from ...registries.registry import ToolDefinition, get_registry_manager
from ...session.notifications import send_notification
from ...session.types import Session
from ...tasks.cancellation import CancellationManager, CancellationToken
from ...tasks.engine import TaskContext, TaskManager, TaskStatus
from ..context import AppContext, RequestContext, SessionContext
from ..payloads import normalize_tool_result
from .invocation import ToolInvocationError, prepare_tool_invocation
from .runners import (
    AsyncToolRunner,
    DedicatedProcessToolRunner,
    ProcessToolRunner,
    SubprocessToolRunner,
    ThreadToolRunner,
    ToolRunner,
)


log = get_logger(__name__)

_ALLOWED_RUNNER_HINTS: Final[frozenset[str]] = frozenset({"async", "thread", "process", "subprocess"})
_DEFAULT_SUBPROCESS_MAX_OUTPUT_BYTES = 64 * 1024


def _get_tool_execution(tool_info: ToolDefinition) -> JSONObject:
    execution = tool_info.execution
    return dict(execution) if isinstance(execution, dict) else {}


def _build_tool_runner(
    *,
    runner_hint: str,
    execution: JSONObject,
    tool_func,
    task_context: TaskContext,
) -> ToolRunner:
    if runner_hint == "async":
        return AsyncToolRunner()

    if runner_hint == "process":
        signature = inspect.signature(tool_func)
        if "cancel_token" in signature.parameters or "task_context" in signature.parameters:
            raise ToolInvocationError(
                MCPErrorCode.INVALID_PARAMS,
                "Invalid params: process runner cannot inject cancel_token/task_context; "
                "use runner=thread/async/subprocess",
            )
        if inspect.iscoroutinefunction(tool_func):
            raise ToolInvocationError(
                MCPErrorCode.INVALID_PARAMS,
                "Invalid params: process runner requires a sync tool implementation",
            )
        cancellation_mode = execution.get("cancellation")
        if cancellation_mode == "terminate":
            return DedicatedProcessToolRunner()
        return ProcessToolRunner()

    if runner_hint == "subprocess":
        streaming = bool(execution.get("streaming", True))
        max_output_bytes = execution.get("maxOutputBytes", _DEFAULT_SUBPROCESS_MAX_OUTPUT_BYTES)
        try:
            max_output_bytes_int = int(max_output_bytes)
        except (TypeError, ValueError):
            max_output_bytes_int = _DEFAULT_SUBPROCESS_MAX_OUTPUT_BYTES
        return SubprocessToolRunner(
            task_context=task_context,
            streaming=streaming,
            max_output_bytes=max(0, max_output_bytes_int),
        )

    return ThreadToolRunner()


async def run_tool_as_task(
    *,
    task_manager: TaskManager,
    session: Session,
    app: FastAPI,
    task_id: str,
    tool_name: str,
    args: JSONObject,
    cancel_token: CancellationToken | None = None,
    cancellation_manager: CancellationManager | None = None,
) -> None:
    task_context: TaskContext | None = None
    payload: JSONObject = {}
    try:
        tool = get_registry_manager(app).get_tool_registry().get(tool_name)
        if tool is None:
            raise ToolInvocationError(MCPErrorCode.METHOD_NOT_FOUND, f"No such tool '{tool_name}'")

        execution = _get_tool_execution(tool)
        runner_hint = execution.get("runner")
        if runner_hint is not None and runner_hint not in _ALLOWED_RUNNER_HINTS:
            raise ToolInvocationError(
                MCPErrorCode.INVALID_PARAMS,
                "Invalid params: execution.runner must be one of async, thread, process, subprocess",
            )

        progress_token = await task_manager.get_progress_token(task_id)
        task_context = TaskContext(
            task_id,
            session,
            task_manager,
            session.queue,
            progress_token=progress_token,
            app=app,
            session_id=session.session_id,
        )
        tool_func, tool_args = prepare_tool_invocation(
            tool_info=tool,
            args=args,
            cancel_token=cancel_token,
            task_context=task_context,
            request_context=RequestContext(
                app_context=AppContext(app),
                session_context=SessionContext(
                    session.session_id,
                    capabilities=session.capabilities,
                    user=session.principal,
                ),
                task_context=task_context,
            ),
        )

        if runner_hint is None:
            runner_hint = "async" if inspect.iscoroutinefunction(tool_func) else "thread"

        runner = _build_tool_runner(
            runner_hint=runner_hint,
            execution=execution,
            tool_func=tool_func,
            task_context=task_context,
        )
        _, result_value = await runner.run(
            tool_func=tool_func,
            tool_args=tool_args,
            task_manager=task_manager,
            task_id=task_id,
            app=app,
        )
        tool_result = cast(JSONObject, normalize_tool_result(result_value))
        payload = {"result": tool_result}
    except ToolInvocationError as exc:
        await task_manager.complete_task(
            task_id,
            status=TaskStatus.FAILED,
            error={"code": exc.code, "message": exc.message},
            status_message=exc.message,
        )
        await task_manager.clear_task_handle(task_id)
        return
    except asyncio.CancelledError:
        await task_manager.complete_task(
            task_id,
            status=TaskStatus.CANCELLED,
            status_message="Task execution was cancelled",
        )
        await task_manager.clear_task_handle(task_id)
        raise
    except Exception as exc:  # pylint: disable=broad-except
        log.exception(
            "[DATA][TOOLS][EXEC] tool_task_failed task_id=%s tool=%s phase=error",
            task_id,
            tool_name,
        )
        await task_manager.complete_task(
            task_id,
            status=TaskStatus.FAILED,
            error={
                "code": MCPErrorCode.INTERNAL_ERROR,
                "message": f"Error executing tool '{tool_name}': {exc}",
            },
            status_message=str(exc),
        )
        await task_manager.clear_task_handle(task_id)
        return
    finally:
        if task_context is not None:
            try:
                await task_context.finish_progress()
            except Exception:
                log.debug("[DATA][PROGRESS][TRACK] finish_progress_failed task_id=%s", task_id)
        if cancellation_manager and cancel_token:
            cancellation_manager.clear(cancel_token.token)

    result_value = payload.get("result")
    error_value = payload.get("error")
    result = result_value if isinstance(result_value, dict) else None
    error = error_value if isinstance(error_value, dict) else None
    status = TaskStatus.COMPLETED
    status_message: str | None = None
    if error:
        status = TaskStatus.FAILED
        message = error.get("message")
        status_message = message if isinstance(message, str) else None
    elif result and result.get("isError"):
        status = TaskStatus.FAILED
        status_message = "Tool execution returned isError=true"

    record = await task_manager.complete_task(
        task_id,
        status=status,
        result=result,
        error=error,
        status_message=status_message,
    )
    if record and session.queue:
        await send_notification(
            session,
            {
                "jsonrpc": "2.0",
                "method": "notifications/tasks/status",
                "params": record.to_wire(),
            },
        )

    await task_manager.clear_task_handle(task_id)


__all__ = ["run_tool_as_task"]
