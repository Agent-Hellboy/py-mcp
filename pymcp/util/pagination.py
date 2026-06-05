"""Cursor-based pagination helpers for MCP list operations."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar


T = TypeVar("T")


def paginate_list(
    items: Sequence[T],
    cursor: str | None,
    *,
    page_size: int = 50,
) -> tuple[list[T], str | None, str | None]:
    """Return a page of items, an optional next cursor, or a cursor error message."""

    start = 0
    if cursor:
        try:
            start = int(cursor)
        except (TypeError, ValueError):
            return [], None, "Invalid cursor"
        if start < 0:
            return [], None, "Invalid cursor"

    items_list = list(items)
    page = items_list[start : start + page_size]
    next_cursor = str(start + page_size) if start + page_size < len(items_list) else None
    return page, next_cursor, None


__all__ = ["paginate_list"]
