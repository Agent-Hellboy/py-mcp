"""Clock helpers: monotonic timers and UTC timestamps."""

from __future__ import annotations

import time
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def monotonic_s() -> float:
    return time.monotonic()


def monotonic_ns() -> int:
    return time.monotonic_ns()


def unix_s() -> float:
    return time.time()


def unix_ms() -> int:
    return time.time_ns() // 1_000_000


def unix_ns() -> int:
    return time.time_ns()


__all__ = ["monotonic_ns", "monotonic_s", "unix_ms", "unix_ns", "unix_s", "utc_now"]
