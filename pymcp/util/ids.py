"""ID generation helpers."""

from __future__ import annotations

from uuid import uuid4


def new_session_id(*, prefix: str | None = None) -> str:
    raw = str(uuid4())
    return f"{prefix}{raw}" if prefix else raw


def new_task_id(*, prefix: str | None = None) -> str:
    raw = str(uuid4())
    return f"{prefix}{raw}" if prefix else raw


__all__ = ["new_session_id", "new_task_id"]
