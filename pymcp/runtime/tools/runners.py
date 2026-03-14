"""Tool execution runners (async/thread/process/subprocess)."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import inspect
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Awaitable, Protocol, TypeGuard, TypeVar, cast

from fastapi import FastAPI

from ...protocol.errors import MCPErrorCode
from ...registries.registry import AsyncToolFunction, SyncToolFunction, ToolFunction
from ...tasks.engine import TaskContext, TaskManager, get_task_executor
from .invocation import ToolArgs, ToolInvocationError


def _get_process_executor(app: FastAPI, max_workers: int | None = None) -> ProcessPoolExecutor:
    if not hasattr(app.state, "tool_process_executor"):
        env_workers = os.getenv("PYMCP_TOOL_PROCESS_WORKERS")
        resolved_workers: int | None = None
        if env_workers:
            try:
                resolved_workers = int(env_workers)
            except ValueError:
                resolved_workers = None
        if resolved_workers is None:
            resolved_workers = max_workers
        app.state.tool_process_executor = ProcessPoolExecutor(max_workers=resolved_workers)
    return cast(ProcessPoolExecutor, app.state.tool_process_executor)


class SubprocessSpec:
    """Description of a subprocess tool execution."""

    def __init__(
        self,
        *,
        argv: list[str] | None = None,
        cmd: str | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool = False,
        timeout_ms: int | None = None,
        combine_stderr: bool = True,
    ):
        self.argv = argv
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.shell = shell
        self.timeout_ms = timeout_ms
        self.combine_stderr = combine_stderr

    def validate(self) -> tuple[bool, str]:
        if self.shell:
            if not self.cmd or not isinstance(self.cmd, str):
                return False, "subprocess spec requires cmd when shell=true"
            return True, ""
        if not self.argv or not isinstance(self.argv, list) or not all(isinstance(arg, str) for arg in self.argv):
            return False, "subprocess spec requires argv: list[str] when shell=false"
        return True, ""


async def _maybe_send_log_line(
    task_context: TaskContext | None,
    *,
    line: str,
    sequence: int,
    streaming: bool,
) -> None:
    if not streaming or not task_context:
        return
    await task_context.send_progress(current=sequence, total=None, message=line)


def _is_async_tool_function(func: ToolFunction) -> TypeGuard[AsyncToolFunction]:
    return inspect.iscoroutinefunction(func)


_ToolResult = TypeVar("_ToolResult")


async def _await_tool_result(awaitable: Awaitable[_ToolResult]) -> _ToolResult:
    return await awaitable


def _run_sync_tool_for_process(tool_func: SyncToolFunction, tool_args: ToolArgs) -> object:
    return tool_func(**tool_args)


async def _discard_stream(stream: asyncio.StreamReader | None) -> None:
    if stream is None:
        return
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            return


class ToolRunner(Protocol):
    async def run(
        self,
        *,
        tool_func: ToolFunction,
        tool_args: ToolArgs,
        task_manager: TaskManager,
        task_id: str,
        app: FastAPI,
    ) -> tuple[asyncio.Future[object], object]:
        ...


class AsyncToolRunner:
    async def run(
        self,
        *,
        tool_func: ToolFunction,
        tool_args: ToolArgs,
        task_manager: TaskManager,
        task_id: str,
        app: FastAPI,
    ) -> tuple[asyncio.Future[object], object]:
        _ = app
        if not _is_async_tool_function(tool_func):
            raise ToolInvocationError(
                MCPErrorCode.INVALID_PARAMS,
                "Invalid params: async runner requires an async tool implementation",
            )
        task: asyncio.Future[object] = asyncio.create_task(_await_tool_result(tool_func(**tool_args)))
        await task_manager.set_task_handle(task_id, task)
        result = await task
        return task, result


class ThreadToolRunner:
    async def run(
        self,
        *,
        tool_func: ToolFunction,
        tool_args: ToolArgs,
        task_manager: TaskManager,
        task_id: str,
        app: FastAPI,
    ) -> tuple[asyncio.Future[object], object]:
        if _is_async_tool_function(tool_func):
            raise ToolInvocationError(
                MCPErrorCode.INVALID_PARAMS,
                "Invalid params: thread runner requires a sync tool implementation",
            )
        sync_tool_func: SyncToolFunction = tool_func
        loop = asyncio.get_running_loop()

        def run_sync() -> object:
            return sync_tool_func(**tool_args)

        executor = get_task_executor(app)
        exec_future: asyncio.Future[object] = loop.run_in_executor(executor, run_sync)
        await task_manager.set_task_handle(task_id, exec_future)
        result = await exec_future
        return exec_future, result


class ProcessToolRunner:
    async def run(
        self,
        *,
        tool_func: ToolFunction,
        tool_args: ToolArgs,
        task_manager: TaskManager,
        task_id: str,
        app: FastAPI,
    ) -> tuple[asyncio.Future[object], object]:
        if _is_async_tool_function(tool_func):
            raise ToolInvocationError(
                MCPErrorCode.INVALID_PARAMS,
                "Invalid params: process runner requires a sync tool implementation",
            )
        sync_tool_func: SyncToolFunction = tool_func
        loop = asyncio.get_running_loop()
        executor = _get_process_executor(app)
        exec_future: asyncio.Future[object] = loop.run_in_executor(
            executor,
            _run_sync_tool_for_process,
            sync_tool_func,
            tool_args,
        )
        await task_manager.set_task_handle(task_id, exec_future)
        result = await exec_future
        return exec_future, result


class DedicatedProcessToolRunner(ProcessToolRunner):
    """Compatibility alias for terminate-style process cancellation."""


class SubprocessToolRunner:
    def __init__(
        self,
        *,
        task_context: TaskContext | None,
        streaming: bool,
        max_output_bytes: int = 64 * 1024,
    ):
        self._task_context = task_context
        self._streaming = streaming
        self._max_output_bytes = max_output_bytes

    async def _build_spec(self, tool_func: ToolFunction, tool_args: ToolArgs) -> SubprocessSpec:
        raw: object
        if _is_async_tool_function(tool_func):
            raw = await tool_func(**tool_args)
        else:
            raw = tool_func(**tool_args)

        if isinstance(raw, SubprocessSpec):
            return raw
        if isinstance(raw, dict):
            raw_argv = raw.get("argv")
            argv = raw_argv if isinstance(raw_argv, list) and all(isinstance(a, str) for a in raw_argv) else None
            cmd = raw.get("cmd") if isinstance(raw.get("cmd"), str) else None
            cwd = raw.get("cwd") if isinstance(raw.get("cwd"), str) else None

            env: dict[str, str] | None = None
            raw_env = raw.get("env")
            if isinstance(raw_env, dict):
                env = {
                    str(key): str(value)
                    for key, value in raw_env.items()
                    if isinstance(key, (str, int)) and str(key) and isinstance(value, (str, int))
                }

            timeout_ms: int | None = None
            raw_timeout = raw.get("timeout_ms")
            if isinstance(raw_timeout, int):
                timeout_ms = raw_timeout
            elif isinstance(raw_timeout, float):
                timeout_ms = int(raw_timeout)

            return SubprocessSpec(
                argv=argv,
                cmd=cmd,
                cwd=cwd,
                env=env,
                shell=bool(raw.get("shell", False)),
                timeout_ms=timeout_ms,
                combine_stderr=bool(raw.get("combine_stderr", True)),
            )

        raise ToolInvocationError(
            MCPErrorCode.INVALID_PARAMS,
            "subprocess runner requires tool to return SubprocessSpec or dict",
        )

    async def run(
        self,
        *,
        tool_func: ToolFunction,
        tool_args: ToolArgs,
        task_manager: TaskManager,
        task_id: str,
        app: FastAPI,
    ) -> tuple[asyncio.Future[object], object]:
        _ = app
        spec = await self._build_spec(tool_func, tool_args)
        ok, err = spec.validate()
        if not ok:
            raise ToolInvocationError(MCPErrorCode.INVALID_PARAMS, f"Invalid params: {err}")

        async def run_subprocess() -> object:
            if spec.shell:
                assert spec.cmd is not None
                proc = await asyncio.create_subprocess_shell(
                    spec.cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT if spec.combine_stderr else asyncio.subprocess.PIPE,
                    cwd=spec.cwd,
                    env=spec.env,
                )
            else:
                assert spec.argv is not None
                proc = await asyncio.create_subprocess_exec(
                    *spec.argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT if spec.combine_stderr else asyncio.subprocess.PIPE,
                    cwd=spec.cwd,
                    env=spec.env,
                )

            assert proc.stdout is not None
            stderr_task = (
                asyncio.create_task(_discard_stream(proc.stderr))
                if proc.stderr is not None
                else None
            )
            collected = bytearray()
            line_no = 0
            try:
                while True:
                    if spec.timeout_ms is not None and spec.timeout_ms > 0:
                        try:
                            line = await asyncio.wait_for(proc.stdout.readline(), timeout=spec.timeout_ms / 1000)
                        except asyncio.TimeoutError:
                            proc.kill()
                            await proc.wait()
                            raise ToolInvocationError(MCPErrorCode.TIMEOUT, "Tool subprocess timed out")
                    else:
                        line = await proc.stdout.readline()

                    if not line:
                        break
                    line_no += 1
                    collected.extend(line)
                    if self._max_output_bytes and len(collected) > self._max_output_bytes:
                        proc.kill()
                        await proc.wait()
                        raise ToolInvocationError(
                            MCPErrorCode.INVALID_PARAMS,
                            "Tool subprocess output exceeded maxOutputBytes",
                        )
                    text = line.decode("utf-8", errors="replace").rstrip("\n")
                    await _maybe_send_log_line(
                        self._task_context,
                        line=text,
                        sequence=line_no,
                        streaming=self._streaming,
                    )

                exit_code = await proc.wait()
                output_text = collected.decode("utf-8", errors="replace")
                if exit_code != 0:
                    raise ToolInvocationError(
                        MCPErrorCode.TOOL_EXECUTION_FAILED,
                        f"Tool subprocess exited with code {exit_code}",
                    )
                return output_text
            finally:
                if stderr_task is not None:
                    with suppress(Exception):
                        await stderr_task

        task: asyncio.Future[object] = asyncio.create_task(run_subprocess())
        await task_manager.set_task_handle(task_id, task)
        result = await task
        return task, result


__all__ = [
    "AsyncToolRunner",
    "DedicatedProcessToolRunner",
    "ProcessToolRunner",
    "SubprocessSpec",
    "SubprocessToolRunner",
    "ThreadToolRunner",
    "ToolRunner",
]
