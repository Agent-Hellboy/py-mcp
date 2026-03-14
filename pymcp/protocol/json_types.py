"""Shared JSON-like protocol types."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import JsonValue as JSONValue


RPCId: TypeAlias = str | int | None
JSONObject: TypeAlias = dict[str, JSONValue]
JSONArray: TypeAlias = list[JSONValue]


__all__ = ["JSONArray", "JSONObject", "JSONValue", "RPCId"]
