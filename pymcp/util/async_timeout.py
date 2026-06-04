"""Async timeout helpers compatible with Python 3.10+."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")


async def await_with_timeout(awaitable: Awaitable[T], timeout: float) -> T:
    if hasattr(asyncio, "timeout"):
        async with asyncio.timeout(timeout):
            return await awaitable
    return await asyncio.wait_for(awaitable, timeout=timeout)


__all__ = ["await_with_timeout"]
