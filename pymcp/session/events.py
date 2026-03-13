"""Event log utilities for stream replay."""

from __future__ import annotations

import os
from collections import deque


DEFAULT_EVENT_HISTORY_LIMIT = int(os.getenv("PYMCP_SSE_HISTORY_LIMIT") or 1000)


def _parse_event_id(event_id: str) -> tuple[str, int] | None:
    try:
        stream_id, seq = event_id.rsplit(":", 1)
        return stream_id, int(seq)
    except (ValueError, TypeError):
        return None


class EventLog:
    """Maintains per-stream event history and counters."""

    def __init__(self, *, limit: int | None = None):
        self._limit = limit if limit is not None else DEFAULT_EVENT_HISTORY_LIMIT
        self._history: deque[tuple[str, str | None, str]] = deque()
        self._counters: dict[str, int] = {}

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def history(self) -> deque[tuple[str, str | None, str]]:
        return self._history

    @property
    def counters(self) -> dict[str, int]:
        return self._counters

    def next_event_id(self, stream_id: str) -> str:
        current = self._counters.get(stream_id, 0)
        next_value = current + 1
        self._counters[stream_id] = next_value
        return f"{stream_id}:{next_value}"

    def record(self, event_id: str, data: str, event_type: str | None = None) -> None:
        self._history.append((event_id, event_type, data))
        while len(self._history) > self._limit:
            self._history.popleft()

    def _has_seen_stream(self, stream_id: str) -> bool:
        return stream_id in self._counters or any(
            isinstance(event_id, str) and event_id.startswith(f"{stream_id}:")
            for (event_id, _, _) in self._history
        )

    def should_resume(self, last_event_id: str | None) -> tuple[str | None, int | None]:
        if not last_event_id:
            return None, None
        parsed = _parse_event_id(last_event_id)
        if not parsed:
            return None, None
        stream_id, seq = parsed
        if not self._has_seen_stream(stream_id):
            return None, None
        return stream_id, seq

    def replay(self, stream_id: str, after_seq: int) -> list[tuple[str, str]]:
        selected: list[tuple[str, str]] = []
        for event_id, _, data in self._history:
            parsed = _parse_event_id(event_id)
            if not parsed:
                continue
            ev_stream_id, ev_seq = parsed
            if ev_stream_id != stream_id or ev_seq <= after_seq:
                continue
            selected.append((event_id, data))
        return selected


__all__ = ["EventLog", "DEFAULT_EVENT_HISTORY_LIMIT"]
