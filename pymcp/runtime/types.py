"""Runtime-layer shared types."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI

from ..capabilities import build_capabilities
from ..protocol.payload import PayloadFactory, get_payload_factory
from ..registries.registry import RegistryManager
from ..session.store import SessionManager
from ..session.types import Session
from ..settings import ServerSettings
from ..tasks.cancellation import CancellationManager
from ..tasks.engine import TaskManager


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
    cancellation_manager: CancellationManager
    task_manager: TaskManager
    direct_response: bool = False
    queue: asyncio.Queue[str] | None = None

    def supports(self, feature: str) -> bool:
        if feature == "roots":
            return True

        capabilities = self._capabilities()

        if feature == "tasks":
            return bool(capabilities.get("tasks")) if isinstance(capabilities, dict) else False

        return feature in capabilities

    def supports_task_request(self, namespace: str, method: str) -> bool:
        capabilities = self._capabilities()
        tasks_caps = capabilities.get("tasks")
        if not isinstance(tasks_caps, dict):
            return False
        requests_caps = tasks_caps.get("requests")
        if not isinstance(requests_caps, dict):
            return False
        namespace_caps = requests_caps.get(namespace)
        if not isinstance(namespace_caps, dict):
            return False
        method_caps = namespace_caps.get(method)
        return isinstance(method_caps, dict)

    def _capabilities(self) -> JSONObject:
        capabilities = self.session.capabilities
        if capabilities is None:
            capabilities = build_capabilities(
                self.server_settings.capabilities,
                self.registry_manager.tool_registry,
                self.registry_manager.prompt_registry,
                self.registry_manager.resource_registry,
            )
        return capabilities

    def payloads(self, *, protocol_version: str | None = None) -> PayloadFactory:
        version = protocol_version or self.session.protocol_version
        return get_payload_factory(version, app=self.app)

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
        queue = self.queue or self.session.queue
        await queue.put(json.dumps(payload))


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
