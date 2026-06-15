"""Tests for MCP log level helpers."""

from pymcp.protocol.logging_levels import normalize_log_level, should_send_log


def test_normalize_log_level():
    assert normalize_log_level("INFO") == "info"
    assert normalize_log_level(" Warning ") == "warning"
    assert normalize_log_level("verbose") is None


def test_should_send_log_respects_minimum_level():
    assert should_send_log("debug", None) is True
    assert should_send_log("debug", "info") is False
    assert should_send_log("info", "info") is True
    assert should_send_log("error", "info") is True
    assert should_send_log("warning", "error") is False
