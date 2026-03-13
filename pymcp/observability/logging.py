"""Centralized logging helpers for the published PyMCP package."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import os
import re
import sys
from types import MappingProxyType
from typing import Final


DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s:%(funcName)s:%(lineno)d %(message)s"

RESET = "\033[0m"
LEVEL_COLORS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
)
LAYER_COLOR = "\033[36m"
DOMAIN_COLOR = "\033[94m"
FLOW_COLOR = "\033[33m"
STATE_COLOR = "\033[35m"


def _use_color() -> bool:
    env = os.getenv("PYMCP_LOG_COLOR")
    if env:
        return env.lower() in {"1", "true", "yes", "on"}
    try:
        return sys.stderr.isatty()
    except (AttributeError, OSError, ValueError):
        return False


class ColorFormatter(logging.Formatter):
    """Lightweight ANSI formatter for MCP-style log tags."""

    TAG_PATTERN = re.compile(r"\[(?P<tag>[A-Z0-9_\-]+)\]")
    STATE_PATTERN = re.compile(r"\b(wait_init|wait_initialized|ready|closed)\b", re.IGNORECASE)

    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)

        level_color = LEVEL_COLORS.get(record.levelname, "")
        if level_color:
            prefix = f"{level_color}{record.levelname}{RESET}"
            formatted = formatted.replace(record.levelname, prefix, 1)

        parts: list[str] = []
        prev = 0
        tag_index = 0
        for match in self.TAG_PATTERN.finditer(formatted):
            parts.append(formatted[prev : match.start()])
            tag_text = match.group(0)
            if tag_index == 0:
                color = LAYER_COLOR
            elif tag_index == 1:
                color = DOMAIN_COLOR
            else:
                color = FLOW_COLOR
            parts.append(f"{color}{tag_text}{RESET}")
            prev = match.end()
            tag_index += 1
        if parts:
            parts.append(formatted[prev:])
            formatted = "".join(parts)

        state_match = self.STATE_PATTERN.search(formatted)
        if state_match:
            token = state_match.group(1)
            formatted = formatted.replace(token, f"{STATE_COLOR}{token}{RESET}", 1)

        return formatted


def _resolve_log_level(level: int | str | None) -> int:
    if isinstance(level, int):
        return level
    if isinstance(level, str) and level:
        parsed = logging._nameToLevel.get(level.upper())  # pylint: disable=protected-access
        if isinstance(parsed, int) and parsed:
            return parsed

    env_level = os.getenv("PYMCP_LOG_LEVEL") or os.getenv("MCP_LOG_LEVEL")
    if env_level:
        parsed = logging._nameToLevel.get(env_level.upper())  # pylint: disable=protected-access
        if isinstance(parsed, int) and parsed:
            return parsed

    candidates = ("uvicorn", "uvicorn.error", "uvicorn.access")
    configured = []
    for name in candidates:
        candidate_level = logging.getLogger(name).level
        if candidate_level != logging.NOTSET:
            configured.append(candidate_level)
    if configured:
        return min(configured)

    return logging.INFO


def configure_logging(level: int | str | None = None, fmt: str = DEFAULT_FORMAT) -> None:
    """Configure the top-level `pymcp` logger."""

    resolved_level = _resolve_log_level(level)
    formatter_cls = ColorFormatter if _use_color() else logging.Formatter
    formatter = formatter_cls(fmt)

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=resolved_level, format=fmt)

    mcp_logger = logging.getLogger("pymcp")
    current_mcp = mcp_logger.level if mcp_logger.level != logging.NOTSET else resolved_level
    mcp_logger.setLevel(min(current_mcp, resolved_level))

    if not mcp_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(resolved_level)
        stream_handler.setFormatter(formatter)
        mcp_logger.addHandler(stream_handler)
    else:
        for existing_handler in mcp_logger.handlers:
            handler_level = existing_handler.level if existing_handler.level != logging.NOTSET else resolved_level
            existing_handler.setLevel(min(handler_level, resolved_level))
            existing_handler.setFormatter(formatter)

    mcp_logger.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger after ensuring the base package logger is configured."""

    configure_logging()
    return logging.getLogger(name)
