"""Compatibility wrapper for the runtime dispatcher."""

from .runtime.dispatch import DispatchError, Dispatcher, process_jsonrpc_message

__all__ = ["DispatchError", "Dispatcher", "process_jsonrpc_message"]
