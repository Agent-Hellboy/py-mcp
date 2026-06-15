"""MCP syslog log level helpers (RFC 5424)."""

from __future__ import annotations

from typing import Final


MCP_LOG_LEVELS: Final[dict[str, int]] = {
    "emergency": 0,
    "alert": 1,
    "critical": 2,
    "error": 3,
    "warning": 4,
    "notice": 5,
    "info": 6,
    "debug": 7,
}


def normalize_log_level(level: str) -> str | None:
    normalized = level.strip().lower()
    if normalized in MCP_LOG_LEVELS:
        return normalized
    return None


def is_valid_log_level(level: str) -> bool:
    return normalize_log_level(level) is not None


def should_send_log(message_level: str, minimum_level: str | None) -> bool:
    """Return whether ``message_level`` meets the session minimum severity."""

    if minimum_level is None:
        return True

    normalized_message = normalize_log_level(message_level)
    normalized_minimum = normalize_log_level(minimum_level)
    if normalized_message is None or normalized_minimum is None:
        return True
    return MCP_LOG_LEVELS[normalized_message] <= MCP_LOG_LEVELS[normalized_minimum]


__all__ = [
    "MCP_LOG_LEVELS",
    "is_valid_log_level",
    "normalize_log_level",
    "should_send_log",
]
