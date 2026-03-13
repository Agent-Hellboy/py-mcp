"""Stdio transport for newline-delimited JSON-RPC."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import sys
from typing import TextIO

from fastapi import FastAPI

from ..runtime.dispatch import process_jsonrpc_message
from ..runtime.payloads import INVALID_REQUEST, PARSE_ERROR, error_response
from ..session import get_session_manager


class StdioTransport:
    """Single-session stdio runner."""

    def __init__(
        self,
        *,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
    ) -> None:
        self._input = input_stream or sys.stdin
        self._output = output_stream or sys.stdout
        self._session_id: str | None = None
        self._write_lock = asyncio.Lock()

    def _ensure_session(self, app: FastAPI) -> str:
        manager = get_session_manager(app)
        if self._session_id is None:
            session = manager.create_session()
            self._session_id = session.session_id
            session.stream_attached = True
            session.attached_stream_id = "stdio"
        else:
            session = manager.get_session(self._session_id)
            if session is not None:
                session.stream_attached = True
                session.attached_stream_id = session.attached_stream_id or "stdio"
        return self._session_id

    async def handle_payload(self, app: FastAPI, payload: dict[str, object]) -> dict[str, object] | None:
        session_id = self._ensure_session(app)
        if "method" not in payload:
            rpc_id = payload.get("id")
            manager = get_session_manager(app)
            if isinstance(rpc_id, str):
                manager.resolve_elicitation_response(session_id, rpc_id, payload)
            return None
        result = await process_jsonrpc_message(
            session_id,
            payload,
            app=app,
            direct_response=True,
        )
        return result.payload

    async def handle_line(self, app: FastAPI, line: str) -> dict[str, object] | None:
        stripped = line.strip()
        if not stripped:
            return None

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return error_response(None, PARSE_ERROR, "Parse error")

        if not isinstance(payload, dict):
            return error_response(None, INVALID_REQUEST, "Invalid JSON-RPC request")

        return await self.handle_payload(app, payload)

    async def _write_line(self, line: str) -> None:
        text = line if line.endswith("\n") else f"{line}\n"
        async with self._write_lock:
            self._output.write(text)
            self._output.flush()

    async def _write_payload(self, payload: dict[str, object]) -> None:
        await self._write_line(json.dumps(payload))

    async def _pump_session_queue(self, app: FastAPI) -> None:
        manager = get_session_manager(app)
        while True:
            session_id = self._session_id
            if session_id is None:
                await asyncio.sleep(0.01)
                continue
            session = manager.get_session(session_id)
            if session is None:
                await asyncio.sleep(0.01)
                continue
            payload = await session.queue.get()
            await self._write_line(payload)

    async def _process_line(self, app: FastAPI, line: str) -> None:
        response = await self.handle_line(app, line)
        if response is None:
            return
        await self._write_payload(response)

    async def run(self, app: FastAPI) -> None:
        loop = asyncio.get_running_loop()
        pending_tasks: set[asyncio.Task[None]] = set()
        queue_task = asyncio.create_task(self._pump_session_queue(app))
        try:
            while True:
                line = await loop.run_in_executor(None, self._input.readline)
                if not line:
                    break
                task = asyncio.create_task(self._process_line(app, line))
                pending_tasks.add(task)
                task.add_done_callback(pending_tasks.discard)
        finally:
            for task in list(pending_tasks):
                task.cancel()
            if pending_tasks:
                with suppress(Exception):
                    await asyncio.gather(*pending_tasks, return_exceptions=True)
            queue_task.cancel()
            with suppress(asyncio.CancelledError):
                await queue_task
            if self._session_id is not None:
                session = get_session_manager(app).get_session(self._session_id)
                if session is not None:
                    session.stream_attached = False
                    session.attached_stream_id = None


def run_stdio_server(
    app: FastAPI,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    transport = StdioTransport(input_stream=input_stream, output_stream=output_stream)
    asyncio.run(transport.run(app))


__all__ = ["StdioTransport", "run_stdio_server"]
