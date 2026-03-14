"""Payload builder helpers for JSON-RPC responses."""

from __future__ import annotations

import base64
import inspect
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, cast

from fastapi import FastAPI

from ..capabilities.registry import ServerCapabilities, get_server_capabilities, negotiate_capabilities
from ..registries.registry import get_registry_manager
from ..settings import SUPPORTED_PROTOCOL_VERSIONS as SERVER_SUPPORTED_PROTOCOL_VERSIONS, ServerSettings
from .errors import MCPErrorCode
from .json_types import JSONValue, JSONObject, RPCId
from .jsonrpc import build_error_envelope, build_result_envelope


SUPPORTED_PROTOCOL_VERSIONS: Final[tuple[str, ...]] = SERVER_SUPPORTED_PROTOCOL_VERSIONS
DEFAULT_PROTOCOL_VERSION: Final[str] = SUPPORTED_PROTOCOL_VERSIONS[0]

def success(rpc_id: RPCId, result: JSONObject) -> JSONObject:
    return build_result_envelope(rpc_id, result)


def error(rpc_id: RPCId, code: int, message: str, *, data: JSONValue | None = None) -> JSONObject:
    return build_error_envelope(rpc_id, code, message, data=data)


def with_meta(payload: JSONObject, meta: JSONObject) -> JSONObject:
    merged = dict(payload)
    merged["_meta"] = meta
    return merged


def negotiate_protocol_version(
    requested_version: str | None,
    settings: ServerSettings | None = None,
) -> tuple[str | None, str | None]:
    supported_versions = (
        tuple(settings.protocol_versions)
        if settings is not None and settings.protocol_versions
        else SUPPORTED_PROTOCOL_VERSIONS
    )
    if not requested_version:
        return supported_versions[0], None
    if requested_version in supported_versions:
        return requested_version, None
    supported = ", ".join(supported_versions)
    return None, f"Unsupported protocolVersion '{requested_version}'. Supported: {supported}"


class PayloadFactory:
    """Version-aware payload builder for MCP JSON-RPC responses."""

    def __init__(self, *, protocol_version: str, app: FastAPI | None = None):
        self.protocol_version = protocol_version or DEFAULT_PROTOCOL_VERSION
        self.app = app

    def success(self, rpc_id: RPCId, result: JSONObject) -> JSONObject:
        return success(rpc_id, result)

    def error(self, rpc_id: RPCId, code: int, message: str, *, data: JSONValue | None = None) -> JSONObject:
        return error(rpc_id, code, message, data=data)

    def success_with_meta(self, rpc_id: RPCId, result: JSONObject, *, meta: JSONObject) -> JSONObject:
        return with_meta(self.success(rpc_id, result), meta)

    def error_with_meta(
        self,
        rpc_id: RPCId,
        code: int,
        message: str,
        *,
        meta: JSONObject,
        data: JSONValue | None = None,
    ) -> JSONObject:
        return with_meta(self.error(rpc_id, code, message, data=data), meta)

    def build_initialize(self, rpc_id: RPCId, client_capabilities: JSONObject | None = None) -> JSONObject:
        server_settings = self._server_settings()
        if self.app:
            server_capabilities = get_server_capabilities(self.app)
        else:
            server_capabilities = ServerCapabilities(capabilities={})  # pragma: no cover - app path used in runtime

        negotiated_capabilities = negotiate_capabilities(client_capabilities, server_capabilities)
        result: JSONObject = {
            "protocolVersion": self.protocol_version,
            "capabilities": negotiated_capabilities,
            "serverInfo": {
                "name": server_settings.name,
                "version": server_settings.version,
            },
        }
        return self.success(rpc_id, result)

    def build_tools_list(self, rpc_id: RPCId) -> JSONObject:
        registry_manager = self._registry_manager()
        return self.success(rpc_id, {"tools": registry_manager.tool_registry.list_payload()})

    def build_prompts_list(self, rpc_id: RPCId) -> JSONObject:
        registry_manager = self._registry_manager()
        return self.success(rpc_id, {"prompts": registry_manager.prompt_registry.list_payload()})

    async def build_prompts_get(
        self,
        rpc_id: RPCId,
        prompt_name: str,
        prompt_arguments: JSONObject,
    ) -> JSONObject:
        registry_manager = self._registry_manager()
        prompt = registry_manager.prompt_registry.get(prompt_name)
        if prompt is None:
            return self.error(rpc_id, MCPErrorCode.INVALID_PARAMS, f"Invalid params: unknown prompt '{prompt_name}'")

        required_args = [arg["name"] for arg in prompt.arguments if arg.get("required")]
        missing = [name for name in required_args if name not in prompt_arguments or prompt_arguments.get(name) is None]
        if missing:
            return self.error(
                rpc_id,
                MCPErrorCode.INVALID_PARAMS,
                f"Missing required argument(s): {', '.join(missing)}",
            )

        try:
            value = prompt.function(**prompt_arguments)
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:  # pylint: disable=broad-except
            return self.error(
                rpc_id,
                MCPErrorCode.INTERNAL_ERROR,
                f"Error generating prompt '{prompt_name}': {exc}",
            )

        if isinstance(value, dict) and "messages" in value:
            result = dict(value)
            result.setdefault("description", prompt.description)
            return self.success(rpc_id, cast(JSONObject, result))

        if isinstance(value, list):
            result = {"description": prompt.description, "messages": value}
            return self.success(rpc_id, cast(JSONObject, result))

        return self.success(
            rpc_id,
            {
                "description": prompt.description,
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": str(value)},
                    }
                ],
            },
        )

    def build_resources_list(self, rpc_id: RPCId) -> JSONObject:
        registry_manager = self._registry_manager()
        return self.success(rpc_id, {"resources": registry_manager.resource_registry.list_payload()})

    async def build_resource_read(self, rpc_id: RPCId, uri: str) -> JSONObject:
        registry_manager = self._registry_manager()
        resource = registry_manager.resource_registry.get(uri)
        if resource is None:
            return self.error(rpc_id, MCPErrorCode.RESOURCE_NOT_FOUND, f"Resource not found: {uri}")

        kwargs: dict[str, str] = {}
        signature = inspect.signature(resource.function)
        if "uri" in signature.parameters:
            kwargs["uri"] = resource.uri

        try:
            value = resource.function(**kwargs)
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:  # pylint: disable=broad-except
            return self.error(rpc_id, MCPErrorCode.INTERNAL_ERROR, f"Error reading resource '{uri}': {exc}")

        if isinstance(value, dict) and "contents" in value:
            return self.success(rpc_id, cast(JSONObject, value))
        if isinstance(value, bytes):
            encoded = base64.b64encode(value).decode("ascii")
            return self.success(
                rpc_id,
                {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": resource.mime_type,
                            "blob": encoded,
                        }
                    ]
                },
            )
        return self.success(
            rpc_id,
            {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": resource.mime_type,
                        "text": value if isinstance(value, str) else str(value),
                    }
                ]
            },
        )

    def build_roots_list(self, rpc_id: RPCId) -> JSONObject:
        roots_config: list[object] = []
        if self.app is not None and hasattr(self.app.state, "roots"):
            roots_config = getattr(self.app.state, "roots", [])

        roots: list[JSONObject] = []
        for root in roots_config:
            if isinstance(root, Mapping):
                uri = root.get("uri")
                name = root.get("name")
            elif isinstance(root, str):
                uri = root
                name = None
            else:
                continue
            if isinstance(uri, str) and uri:
                payload: JSONObject = {"uri": uri}
                if isinstance(name, str) and name:
                    payload["name"] = name
                roots.append(payload)

        return self.success(rpc_id, {"roots": roots})

    def _registry_manager(self):
        if self.app is None:
            raise RuntimeError("PayloadFactory requires app-bound registry access")
        return get_registry_manager(self.app)

    def _server_settings(self) -> ServerSettings:
        if self.app is not None and hasattr(self.app.state, "server_settings"):
            return cast(ServerSettings, self.app.state.server_settings)
        return ServerSettings()


_FACTORY_BY_PROTOCOL_VERSION: Final[Mapping[str, type[PayloadFactory]]] = MappingProxyType(
    {version: PayloadFactory for version in SUPPORTED_PROTOCOL_VERSIONS}
)


def get_payload_factory(protocol_version: str | None, *, app: FastAPI | None = None) -> PayloadFactory:
    settings = (
        cast(ServerSettings, app.state.server_settings)
        if app is not None and hasattr(app.state, "server_settings")
        else None
    )
    version, error_message = negotiate_protocol_version(protocol_version, settings)
    if version is None:
        raise ValueError(error_message or "Unsupported protocolVersion")
    factory_cls = _FACTORY_BY_PROTOCOL_VERSION.get(version, PayloadFactory)
    return factory_cls(protocol_version=version, app=app)


__all__ = [
    "DEFAULT_PROTOCOL_VERSION",
    "PayloadFactory",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "error",
    "get_payload_factory",
    "negotiate_protocol_version",
    "success",
    "with_meta",
]
