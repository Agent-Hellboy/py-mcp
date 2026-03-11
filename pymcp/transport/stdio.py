"""Stdio transport for newline-delimited JSON-RPC."""

from __future__ import annotations

import asyncio
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

    def _ensure_session(self, app: FastAPI) -> str:
        if self._session_id is None:
            session = get_session_manager(app).create_session()
            self._session_id = session.session_id
        return self._session_id

    async def handle_payload(self, app: FastAPI, payload: dict[str, object]) -> dict[str, object] | None:
        session_id = self._ensure_session(app)
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

    async def run(self, app: FastAPI) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, self._input.readline)
            if not line:
                break
            response = await self.handle_line(app, line)
            if response is None:
                continue
            self._output.write(json.dumps(response) + "\n")
            self._output.flush()


def run_stdio_server(
    app: FastAPI,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    transport = StdioTransport(input_stream=input_stream, output_stream=output_stream)
    asyncio.run(transport.run(app))


__all__ = ["StdioTransport", "run_stdio_server"]
