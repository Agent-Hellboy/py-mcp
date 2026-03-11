"""Registries for tools, prompts, and resources."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, get_args, get_origin


JSONSchema = dict[str, Any]
SyncOrAsyncCallable = Callable[..., Any]
Listener = Callable[[], None]


def _normalize_annotation(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    if origin is list:
        return list
    if origin is tuple:
        return tuple
    if origin is dict:
        return dict
    if origin is set:
        return list
    if str(origin) in {"typing.Union", "types.UnionType"}:
        members = [member for member in get_args(annotation) if member is not type(None)]
        return members[0] if members else annotation
    return annotation


def _annotation_to_schema(annotation: Any) -> JSONSchema:
    annotation = _normalize_annotation(annotation)
    if annotation in {int, float}:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}
    if annotation is dict:
        return {"type": "object"}
    if annotation in {list, tuple, set}:
        return {"type": "array"}
    return {"type": "string"}


def _schema_from_signature(func: SyncOrAsyncCallable) -> JSONSchema:
    schema: JSONSchema = {"type": "object", "properties": {}, "required": []}
    signature = inspect.signature(func)
    for name, parameter in signature.parameters.items():
        properties = schema["properties"]
        if not isinstance(properties, dict):
            continue
        properties[name] = _annotation_to_schema(parameter.annotation)
        if parameter.default is inspect.Parameter.empty:
            required = schema["required"]
            if isinstance(required, list):
                required.append(name)
    return schema


def _arguments_from_signature(func: SyncOrAsyncCallable) -> list[dict[str, Any]]:
    arguments: list[dict[str, Any]] = []
    signature = inspect.signature(func)
    for name, parameter in signature.parameters.items():
        arguments.append(
            {
                "name": name,
                "required": parameter.default is inspect.Parameter.empty,
                "description": "",
                "schema": _annotation_to_schema(parameter.annotation),
            }
        )
    return arguments


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: JSONSchema
    function: SyncOrAsyncCallable
    prompt: bool

    def to_mcp_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "prompt": self.prompt,
        }


@dataclass(slots=True)
class PromptDefinition:
    name: str
    description: str
    arguments: list[dict[str, Any]]
    function: SyncOrAsyncCallable

    def to_mcp_payload(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "description": self.description,
            "arguments": [],
        }
        args: list[dict[str, Any]] = []
        for argument in self.arguments:
            args.append(
                {
                    "name": argument["name"],
                    "description": argument.get("description", ""),
                    "required": bool(argument.get("required", False)),
                }
            )
        payload["arguments"] = args
        return payload


@dataclass(slots=True)
class ResourceDefinition:
    uri: str
    name: str
    description: str
    mime_type: str
    function: SyncOrAsyncCallable

    def to_mcp_payload(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class _RegistryBase:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def add_listener(self, listener: Listener) -> None:
        if callable(listener):
            self._listeners.append(listener)

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                continue


class ToolRegistry(_RegistryBase):
    def __init__(self) -> None:
        super().__init__()
        self._tools: dict[str, ToolDefinition] = {}

    def register(
        self,
        func: SyncOrAsyncCallable | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable[[SyncOrAsyncCallable], SyncOrAsyncCallable] | SyncOrAsyncCallable:
        if func is None:
            return lambda callback: self.register(callback, name=name, description=description)

        tool_name = name or func.__name__
        tool_description = (description if description is not None else (func.__doc__ or "")).strip()
        definition = ToolDefinition(
            name=tool_name,
            description=tool_description,
            input_schema=_schema_from_signature(func),
            function=func,
            prompt="prompt" in inspect.signature(func).parameters,
        )
        self._tools[tool_name] = definition
        self._notify_listeners()
        return func

    def clear(self) -> None:
        self._tools.clear()

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def definitions(self) -> dict[str, ToolDefinition]:
        return dict(self._tools)

    def import_tools(self, tools: dict[str, ToolDefinition]) -> None:
        self._tools.update(tools)

    def get_tools(self) -> dict[str, dict[str, Any]]:
        payload: dict[str, dict[str, Any]] = {}
        for name, tool in self._tools.items():
            payload[name] = {
                "function": tool.function,
                "description": tool.description,
                "inputSchema": tool.input_schema,
                "prompt": tool.prompt,
            }
        return payload

    def list_payload(self) -> list[dict[str, Any]]:
        return [tool.to_mcp_payload() for tool in self._tools.values()]


class PromptRegistry(_RegistryBase):
    def __init__(self) -> None:
        super().__init__()
        self._prompts: dict[str, PromptDefinition] = {}

    def register(
        self,
        func: SyncOrAsyncCallable | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        arguments: list[dict[str, Any]] | None = None,
    ) -> Callable[[SyncOrAsyncCallable], SyncOrAsyncCallable] | SyncOrAsyncCallable:
        if func is None:
            return lambda callback: self.register(
                callback,
                name=name,
                description=description,
                arguments=arguments,
            )

        prompt_name = name or func.__name__
        prompt_description = (description if description is not None else (func.__doc__ or "")).strip()
        definition = PromptDefinition(
            name=prompt_name,
            description=prompt_description,
            arguments=arguments or _arguments_from_signature(func),
            function=func,
        )
        self._prompts[prompt_name] = definition
        self._notify_listeners()
        return func

    def clear(self) -> None:
        self._prompts.clear()

    def get(self, name: str) -> PromptDefinition | None:
        return self._prompts.get(name)

    def definitions(self) -> dict[str, PromptDefinition]:
        return dict(self._prompts)

    def import_prompts(self, prompts: dict[str, PromptDefinition]) -> None:
        self._prompts.update(prompts)

    def get_prompts(self) -> dict[str, PromptDefinition]:
        return dict(self._prompts)

    def list_payload(self) -> list[dict[str, Any]]:
        return [prompt.to_mcp_payload() for prompt in self._prompts.values()]


class ResourceRegistry(_RegistryBase):
    def __init__(self) -> None:
        super().__init__()
        self._resources: dict[str, ResourceDefinition] = {}

    def register(
        self,
        *,
        uri: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str = "text/plain",
    ) -> Callable[[SyncOrAsyncCallable], SyncOrAsyncCallable]:
        def decorator(func: SyncOrAsyncCallable) -> SyncOrAsyncCallable:
            resource_name = name or func.__name__
            resource_description = (description if description is not None else (func.__doc__ or "")).strip()
            definition = ResourceDefinition(
                uri=uri,
                name=resource_name,
                description=resource_description,
                mime_type=mime_type,
                function=func,
            )
            self._resources[uri] = definition
            self._notify_listeners()
            return func

        return decorator

    def clear(self) -> None:
        self._resources.clear()

    def get(self, uri: str) -> ResourceDefinition | None:
        return self._resources.get(uri)

    def definitions(self) -> dict[str, ResourceDefinition]:
        return dict(self._resources)

    def import_resources(self, resources: dict[str, ResourceDefinition]) -> None:
        self._resources.update(resources)

    def get_resources(self) -> dict[str, ResourceDefinition]:
        return dict(self._resources)

    def list_payload(self) -> list[dict[str, Any]]:
        return [resource.to_mcp_payload() for resource in self._resources.values()]


class RegistryManager:
    """Application-scoped access to tool, prompt, and resource registries."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
        prompt_registry: PromptRegistry | None = None,
        resource_registry: ResourceRegistry | None = None,
    ) -> None:
        self.tool_registry = tool_registry or ToolRegistry()
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.resource_registry = resource_registry or ResourceRegistry()

    def copy_from_global_registries(
        self,
        global_tools: ToolRegistry,
        global_prompts: PromptRegistry,
        global_resources: ResourceRegistry,
    ) -> None:
        self.tool_registry.import_tools(global_tools.definitions())
        self.prompt_registry.import_prompts(global_prompts.definitions())
        self.resource_registry.import_resources(global_resources.definitions())

    def get_tool_registry(self) -> ToolRegistry:
        return self.tool_registry

    def get_prompt_registry(self) -> PromptRegistry:
        return self.prompt_registry

    def get_resource_registry(self) -> ResourceRegistry:
        return self.resource_registry


def dump_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


tool_registry = ToolRegistry()
prompt_registry = PromptRegistry()
resource_registry = ResourceRegistry()


def get_registry_manager(app: Any) -> RegistryManager:
    if not hasattr(app.state, "registry_manager"):
        manager = RegistryManager()
        manager.copy_from_global_registries(tool_registry, prompt_registry, resource_registry)
        app.state.registry_manager = manager
    return app.state.registry_manager


__all__ = [
    "PromptDefinition",
    "PromptRegistry",
    "RegistryManager",
    "ResourceDefinition",
    "ResourceRegistry",
    "ToolDefinition",
    "ToolRegistry",
    "dump_value",
    "get_registry_manager",
    "prompt_registry",
    "resource_registry",
    "tool_registry",
]
