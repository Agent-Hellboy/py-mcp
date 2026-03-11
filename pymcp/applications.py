"""Compatibility wrapper for the runtime app factory."""

from .runtime.server import create_app

__all__ = ["create_app"]
