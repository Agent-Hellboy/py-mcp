"""Runtime-layer shared types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from ..capabilities import build_capabilities
from ..registries.registry import RegistryManager
from ..session.store import SessionManager
from ..session.types import Session
from ..settings import ServerSettings


JSONObject = dict[str, Any]


@dataclass(frozen=True)
class DispatchResponse:
    status: int
    json: bool
    payload: JSONObject | None


DispatchResult = DispatchResponse


@dataclass(frozen=True)
class DispatchContext:
    session_id: str
    data: JSONObject
    app: FastAPI
    session: Session
    rpc_id: Any
    method: str
    registry_manager: RegistryManager
    server_settings: ServerSettings
    session_manager: SessionManager
    direct_response: bool = False

    def supports(self, feature: str) -> bool:
        capabilities = build_capabilities(
            self.server_settings.capabilities,
            self.registry_manager.tool_registry,
            self.registry_manager.prompt_registry,
            self.registry_manager.resource_registry,
        )
        return feature in capabilities

    async def maybe_enqueue(
        self,
        payload: JSONObject | None,
        *,
        require_id: bool = True,
    ) -> None:
        if self.direct_response or payload is None:
            return
        if require_id and "id" not in self.data:
            return
        await self.session.queue.put(json.dumps(payload))


def make_result(
    status: int,
    *,
    json_response: bool,
    payload: JSONObject | None,
) -> DispatchResult:
    return DispatchResponse(status=status, json=json_response, payload=payload)


__all__ = [
    "DispatchContext",
    "DispatchResponse",
    "DispatchResult",
    "JSONObject",
    "make_result",
]
