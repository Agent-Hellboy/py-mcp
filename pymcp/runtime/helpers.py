"""Shared helpers for runtime dispatch and handlers."""

from __future__ import annotations

import inspect
from typing import Any

from ..settings import ServerSettings


def ensure_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def select_protocol_version(requested: Any, settings: ServerSettings) -> str:
    if isinstance(requested, str) and requested in settings.protocol_versions:
        return requested
    return settings.protocol_versions[0]


__all__ = ["ensure_mapping", "maybe_await", "select_protocol_version"]
