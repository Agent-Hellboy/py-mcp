"""Runtime safety limits (queue sizes, timeouts, payload bounds)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import cast

from fastapi import FastAPI


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    session_outbound_queue_maxsize: int = 1000
    max_request_bytes: int | None = None
    tool_max_output_bytes: int = 64 * 1024
    tool_default_timeout_ms: int | None = None

    @classmethod
    def from_env(cls) -> "RuntimeLimits":
        defaults = cls()
        session_q = _env_int("PYMCP_SESSION_OUTBOUND_QUEUE_MAXSIZE")
        max_req = _env_int("PYMCP_MAX_REQUEST_BYTES")
        tool_out = _env_int("PYMCP_TOOL_MAX_OUTPUT_BYTES")
        tool_timeout = _env_int("PYMCP_TOOL_DEFAULT_TIMEOUT_MS")
        return cls(
            session_outbound_queue_maxsize=(
                session_q if session_q is not None else defaults.session_outbound_queue_maxsize
            ),
            max_request_bytes=max_req,
            tool_max_output_bytes=tool_out if tool_out is not None else defaults.tool_max_output_bytes,
            tool_default_timeout_ms=tool_timeout,
        )


@lru_cache(maxsize=1)
def _get_env_runtime_limits() -> RuntimeLimits:
    return RuntimeLimits.from_env()


def get_runtime_limits(app: FastAPI | None = None) -> RuntimeLimits:
    if app is None or not hasattr(app, "state"):
        return _get_env_runtime_limits()
    if not hasattr(app.state, "runtime_limits"):
        app.state.runtime_limits = RuntimeLimits.from_env()
    return cast(RuntimeLimits, app.state.runtime_limits)


__all__ = ["RuntimeLimits", "get_runtime_limits"]
