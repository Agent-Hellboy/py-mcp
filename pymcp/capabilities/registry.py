"""Capability declarations and negotiation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, cast

from fastapi import FastAPI

from ..settings import CapabilitySettings

if TYPE_CHECKING:
    from ..registries.registry import PromptRegistry, ResourceRegistry, ToolRegistry


JSONObject = dict[str, Any]


# ---------------------------------------------------------------------------
# Server capability providers
# ---------------------------------------------------------------------------


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
class LoggingCapability:
    enabled: bool = False

    def get_capabilities(self) -> JSONObject:
        if not self.enabled:
            return {}
        return {"logging": {}}


@dataclass(slots=True)
class CompletionsCapability:
    enabled: bool = False

    def get_capabilities(self) -> JSONObject:
        if not self.enabled:
            return {}
        return {"completions": {}}


@dataclass(slots=True)
class ServerTasksCapability:
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
class ServerExperimentalCapability:
    features: dict[str, JSONObject] | None = None

    def get_capabilities(self) -> JSONObject:
        if not self.features:
            return {}
        return {"experimental": dict(self.features)}


# ---------------------------------------------------------------------------
# build_capabilities – assembles the *server* capability declaration
# ---------------------------------------------------------------------------


def build_capabilities(
    settings: CapabilitySettings,
    tools: "ToolRegistry",
    prompts: "PromptRegistry",
    resources: "ResourceRegistry",
) -> JSONObject:
    """Build the server capability declaration for the current registries/settings.

    Per the MCP 2025-11-25 spec, server capabilities are: tools, prompts,
    resources, logging, completions, tasks (server-side), and experimental.
    Client-only capabilities (roots, sampling, elicitation) are NOT included.
    """

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
            available=bool(resources.get_resources()) or bool(resources.get_templates()),
        ),
        LoggingCapability(enabled=settings.logging_enabled),
        CompletionsCapability(enabled=settings.completions_enabled),
        ServerTasksCapability(
            enabled=settings.tasks_enabled,
            tools_call=settings.tasks_tool_call,
            list_supported=settings.tasks_list,
            cancel_supported=settings.tasks_cancel,
        ),
        ServerExperimentalCapability(features=settings.experimental_features),
    ]

    capabilities: JSONObject = {}
    for provider in providers:
        capabilities.update(provider.get_capabilities())
    return capabilities


# ---------------------------------------------------------------------------
# ServerCapabilities – app-aware wrapper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# ClientCapabilities – parsed from the initialize request
# ---------------------------------------------------------------------------


class ClientCapabilities:
    """Client capability declarations from the initialize request.

    Per the MCP 2025-11-25 spec, client capabilities include: roots, sampling,
    elicitation, tasks (client-side), and experimental.
    """

    def __init__(self, capabilities: JSONObject | None = None):
        self.capabilities = dict(capabilities or {})

    # -- generic ---------------------------------------------------------

    def supports(self, feature: str) -> bool:
        """Check whether the client declared support for *feature*.

        Tasks require explicit opt-in.  For other features, absence means
        the client did not declare them (treat as unsupported for outbound
        gating).
        """
        if feature == "tasks":
            return "tasks" in self.capabilities
        return feature in self.capabilities

    def get_capabilities(self) -> JSONObject:
        return dict(self.capabilities)

    # -- roots -----------------------------------------------------------

    def supports_roots(self) -> bool:
        return "roots" in self.capabilities

    def supports_roots_list_changed(self) -> bool:
        roots = self.capabilities.get("roots")
        if not isinstance(roots, dict):
            return False
        return bool(roots.get("listChanged"))

    # -- sampling --------------------------------------------------------

    def supports_sampling(self) -> bool:
        return "sampling" in self.capabilities

    def supports_sampling_tools(self) -> bool:
        sampling = self.capabilities.get("sampling")
        if not isinstance(sampling, dict):
            return False
        return "tools" in sampling

    # -- elicitation -----------------------------------------------------

    def supports_elicitation(self, mode: str | None = None) -> bool:
        """Return True if the client supports elicitation.

        If *mode* is given (``"form"`` or ``"url"``), check that specific
        mode.  An empty ``elicitation: {}`` object is treated as
        ``form``-only for backwards compatibility with the spec.
        """
        elicit = self.capabilities.get("elicitation")
        if elicit is None:
            return False
        if mode is None:
            return True
        if not isinstance(elicit, dict) or not elicit:
            # Empty dict == form-only per spec backwards compatibility
            return mode == "form"
        return mode in elicit

    # -- client-side tasks -----------------------------------------------

    def supports_client_tasks(self) -> bool:
        return "tasks" in self.capabilities

    def supports_task_request(self, namespace: str, method: str) -> bool:
        """Check client task-augmented request support.

        E.g. ``supports_task_request("elicitation", "create")`` checks
        ``capabilities.tasks.requests.elicitation.create``.
        """
        tasks = self.capabilities.get("tasks")
        if not isinstance(tasks, dict):
            return False
        requests = tasks.get("requests")
        if not isinstance(requests, dict):
            return False
        ns = requests.get(namespace)
        if not isinstance(ns, dict):
            return False
        return method in ns

    # -- experimental ----------------------------------------------------

    def supports_experimental(self, key: str) -> bool:
        exp = self.capabilities.get("experimental")
        if not isinstance(exp, dict):
            return False
        return key in exp


# ---------------------------------------------------------------------------
# Negotiation
# ---------------------------------------------------------------------------


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
    "CompletionsCapability",
    "LoggingCapability",
    "PromptsCapability",
    "ResourcesCapability",
    "ServerCapabilities",
    "ServerExperimentalCapability",
    "ServerTasksCapability",
    "ToolsCapability",
    "build_capabilities",
    "get_server_capabilities",
    "negotiate_capabilities",
]
