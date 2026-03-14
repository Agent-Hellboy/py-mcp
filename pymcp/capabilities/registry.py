"""Capability declarations and negotiation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

from fastapi import FastAPI

from ..settings import CapabilitySettings

if TYPE_CHECKING:
    from ..registries.registry import PromptRegistry, ResourceRegistry, ToolRegistry


JSONObject = dict[str, Any]


class CapabilityProvider(Protocol):
    """Provides a capabilities fragment."""

    def get_capabilities(self) -> JSONObject:
        ...


@dataclass(slots=True)
class ToolsCapability:
    list_changed: bool = False

    def get_capabilities(self) -> JSONObject:
        return {"tools": {"listChanged": self.list_changed}}


@dataclass(slots=True)
class PromptsCapability:
    list_changed: bool = False
    advertise_empty: bool = False
    available: bool = True

    def get_capabilities(self) -> JSONObject:
        if not self.available and not self.advertise_empty:
            return {}
        return {"prompts": {"listChanged": self.list_changed}}


@dataclass(slots=True)
class ResourcesCapability:
    list_changed: bool = False
    subscribe: bool = False
    advertise_empty: bool = False
    available: bool = True

    def get_capabilities(self) -> JSONObject:
        if not self.available and not self.advertise_empty:
            return {}
        return {
            "resources": {
                "listChanged": self.list_changed,
                "subscribe": self.subscribe,
            }
        }


@dataclass(slots=True)
class RootsCapability:
    list_changed: bool = False
    enabled: bool = True

    def get_capabilities(self) -> JSONObject:
        if not self.enabled:
            return {}
        return {"roots": {"listChanged": self.list_changed}}


@dataclass(slots=True)
class TasksCapability:
    enabled: bool = False
    tools_call: bool = True
    list_supported: bool = True
    cancel_supported: bool = True

    def get_capabilities(self) -> JSONObject:
        if not self.enabled:
            return {}
        tasks: JSONObject = {}
        if self.list_supported:
            tasks["list"] = {}
        if self.cancel_supported:
            tasks["cancel"] = {}
        if self.tools_call:
            tasks["requests"] = {"tools": {"call": {}}}
        return {"tasks": tasks}


@dataclass(slots=True)
class ElicitationCapability:
    form: bool = False
    url: bool = False

    def get_capabilities(self) -> JSONObject:
        modes: JSONObject = {}
        if self.form:
            modes["form"] = {}
        if self.url:
            modes["url"] = {}
        if not modes:
            return {}
        return {"elicitation": modes}


def build_capabilities(
    settings: CapabilitySettings,
    tools: "ToolRegistry",
    prompts: "PromptRegistry",
    resources: "ResourceRegistry",
) -> JSONObject:
    """Build the server capability declaration for the current registries/settings."""

    providers: list[CapabilityProvider] = [
        ToolsCapability(list_changed=settings.tools_list_changed),
        PromptsCapability(
            list_changed=settings.prompts_list_changed,
            advertise_empty=settings.advertise_empty_prompts,
            available=bool(prompts.get_prompts()),
        ),
        ResourcesCapability(
            list_changed=settings.resources_list_changed,
            subscribe=settings.resources_subscribe,
            advertise_empty=settings.advertise_empty_resources,
            available=bool(resources.get_resources()),
        ),
        RootsCapability(
            list_changed=settings.roots_list_changed,
            enabled=settings.roots_enabled,
        ),
        TasksCapability(
            enabled=settings.tasks_enabled,
            tools_call=settings.tasks_tool_call,
            list_supported=settings.tasks_list,
            cancel_supported=settings.tasks_cancel,
        ),
        ElicitationCapability(
            form=settings.elicitation_form,
            url=settings.elicitation_url,
        ),
    ]

    capabilities: JSONObject = {}
    for provider in providers:
        capabilities.update(provider.get_capabilities())
    return capabilities


class ServerCapabilities:
    """App-aware capability wrapper used by the runtime and notification hooks."""

    def __init__(
        self,
        *,
        app: FastAPI | None = None,
        capabilities: JSONObject | None = None,
    ) -> None:
        self._app = app
        self._capabilities = capabilities

    def get_capabilities(self) -> JSONObject:
        if self._capabilities is not None:
            return dict(self._capabilities)
        if self._app is None:
            return {}

        from ..registries.registry import get_registry_manager

        server_settings = getattr(self._app.state, "server_settings", None)
        if server_settings is None:
            return {}
        registry_manager = get_registry_manager(self._app)
        return build_capabilities(
            server_settings.capabilities,
            registry_manager.tool_registry,
            registry_manager.prompt_registry,
            registry_manager.resource_registry,
        )


class ClientCapabilities:
    """Client capability declarations from the initialize request."""

    def __init__(self, capabilities: JSONObject | None = None):
        self.capabilities = dict(capabilities or {})

    def supports(self, feature: str) -> bool:
        if feature == "tasks":
            return bool(self.capabilities.get("tasks"))
        if feature == "roots":
            return True
        if feature not in self.capabilities:
            return True
        value = self.capabilities.get(feature)
        if isinstance(value, bool):
            return value
        return True

    def get_capabilities(self) -> JSONObject:
        return dict(self.capabilities)


def negotiate_capabilities(
    client_caps: JSONObject | None,
    server_caps: ServerCapabilities,
) -> JSONObject:
    """Return the server capabilities exposed to the client.

    This currently does not intersect nested capability fragments. The server is
    authoritative and the dispatcher enforces strict behavior for capabilities
    like tasks where negotiation matters.
    """

    _ = client_caps
    return server_caps.get_capabilities()


def get_server_capabilities(app: FastAPI) -> ServerCapabilities:
    if not hasattr(app.state, "server_capabilities"):
        app.state.server_capabilities = ServerCapabilities(app=app)
    return cast(ServerCapabilities, app.state.server_capabilities)


__all__ = [
    "ClientCapabilities",
    "ElicitationCapability",
    "PromptsCapability",
    "ResourcesCapability",
    "RootsCapability",
    "ServerCapabilities",
    "TasksCapability",
    "ToolsCapability",
    "build_capabilities",
    "get_server_capabilities",
    "negotiate_capabilities",
]
