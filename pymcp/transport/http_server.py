"""Uvicorn entrypoint with MCP-friendly shutdown defaults."""

from __future__ import annotations

from typing import Any

import uvicorn
from fastapi import FastAPI


def run_http_server(
    app: FastAPI,
    *,
    host: str = "0.0.0.0",
    port: int = 8088,
    timeout_graceful_shutdown: float = 2.0,
    **kwargs: Any,
) -> None:
    """Run the MCP HTTP app; SSE streams exit quickly on SIGINT via app lifespan."""
    uvicorn.run(
        app,
        host=host,
        port=port,
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        **kwargs,
    )


__all__ = ["run_http_server"]
