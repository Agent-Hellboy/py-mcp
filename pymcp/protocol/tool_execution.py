"""Types for tool execution metadata included in tool definitions."""

from __future__ import annotations

from typing import Literal, TypedDict


class ToolExecutionConfig(TypedDict, total=False):
    """Optional execution metadata for tools."""

    taskSupport: Literal["required", "optional", "forbidden"]
    runner: Literal["async", "thread", "process", "subprocess"]
    cancellation: Literal["cooperative", "terminate"]
    streaming: bool
    maxOutputBytes: int


__all__ = ["ToolExecutionConfig"]
