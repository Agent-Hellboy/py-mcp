"""Registries for tools, prompts, and resources."""

from __future__ import annotations

import inspect
import json
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, ParamSpec, Sequence, TypeVar, cast, get_args, get_origin, overload

from ..protocol.tool_execution import ToolExecutionConfig


JSONSchema = dict[str, Any]
SyncOrAsyncCallable = Callable[..., Any]
SyncToolFunction = Callable[..., object]
AsyncToolFunction = Callable[..., Awaitable[object]]
ToolFunction = SyncToolFunction | AsyncToolFunction
Listener = Callable[[], None]
ListChangedListener = Callable[[], None]
ResourceUpdatedListener = Callable[[str], None]

_P = ParamSpec("_P")
_R = TypeVar("_R", bound=object)
_ToolFuncT = TypeVar("_ToolFuncT", bound=ToolFunction)

_INTERNAL_TOOL_PARAMS = frozenset({"cancel_token", "task_context", "request_context"})


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
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
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
        if name in _INTERNAL_TOOL_PARAMS:
            continue
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


def _notify_listeners(listeners: Sequence[ListChangedListener]) -> None:
    for listener in list(listeners):
        try:
            listener()
        except Exception:
            continue


def _notify_update_listeners(listeners: Sequence[ResourceUpdatedListener], uri: str) -> None:
    for listener in list(listeners):
        try:
            listener(uri)
        except Exception:
            continue


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: JSONSchema
    function: SyncOrAsyncCallable
    prompt: bool
    execution: ToolExecutionConfig | None = None

    def to_mcp_payload(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.execution:
            payload["execution"] = dict(self.execution)
        return payload


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
        _notify_listeners(self._listeners)


class ToolRegistry(_RegistryBase):
    def __init__(self) -> None:
        super().__init__()
        self._tools: dict[str, ToolDefinition] = {}

    def clear(self) -> None:
        if not self._tools:
            return
        self._tools.clear()
        self._notify_listeners()

    def _register_tool(
        self,
        func: _ToolFuncT,
        *,
        name: str | None = None,
        description: str | None = None,
        execution: ToolExecutionConfig | None = None,
    ) -> _ToolFuncT:
        manager = get_current_registry_manager()
        if manager is not None and manager.tool_registry is not self:
            return manager.tool_registry.register(
                func,
                name=name,
                description=description,
                execution=execution,
            )

        tool_name = name or func.__name__
        tool_description = (description if description is not None else (func.__doc__ or "")).strip()
        definition = ToolDefinition(
            name=tool_name,
            description=tool_description,
            input_schema=_schema_from_signature(func),
            function=func,
            prompt="prompt" in inspect.signature(func).parameters,
            execution=execution,
        )
        self._tools[tool_name] = definition
        self._notify_listeners()
        return func

    @overload
    def register(
        self,
        func: _ToolFuncT,
        *,
        name: str | None = None,
        description: str | None = None,
        execution: ToolExecutionConfig | None = None,
    ) -> _ToolFuncT:
        ...

    @overload
    def register(
        self,
        func: None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        execution: ToolExecutionConfig | None = None,
    ) -> Callable[[_ToolFuncT], _ToolFuncT]:
        ...

    def register(
        self,
        func: _ToolFuncT | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        execution: ToolExecutionConfig | None = None,
    ) -> Callable[[_ToolFuncT], _ToolFuncT] | _ToolFuncT:
        if func is None:
            return lambda callback: self._register_tool(
                callback,
                name=name,
                description=description,
                execution=execution,
            )
        return self._register_tool(
            func,
            name=name,
            description=description,
            execution=execution,
        )

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self.get(name)

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
                "execution": tool.execution,
            }
        return payload

    def list_payload(self) -> list[dict[str, Any]]:
        return [tool.to_mcp_payload() for tool in self._tools.values()]


class PromptRegistry(_RegistryBase):
    def __init__(self) -> None:
        super().__init__()
        self._prompts: dict[str, PromptDefinition] = {}

    def clear(self) -> None:
        if not self._prompts:
            return
        self._prompts.clear()
        self._notify_listeners()

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

        manager = get_current_registry_manager()
        if manager is not None and manager.prompt_registry is not self:
            return manager.prompt_registry.register(
                func,
                name=name,
                description=description,
                arguments=arguments,
            )

        prompt_name = name or func.__name__
        prompt_description = (description if description is not None else (func.__doc__ or "")).strip()
        definition = PromptDefinition(
            name=prompt_name,
            description=prompt_description,
            arguments=arguments if arguments is not None else _arguments_from_signature(func),
            function=func,
        )
        self._prompts[prompt_name] = definition
        self._notify_listeners()
        return func

    def get(self, name: str) -> PromptDefinition | None:
        return self._prompts.get(name)

    def get_prompt(self, name: str) -> PromptDefinition | None:
        return self.get(name)

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
        self._update_listeners: list[ResourceUpdatedListener] = []

    def clear(self) -> None:
        if not self._resources:
            return
        self._resources.clear()
        self._notify_listeners()

    def add_update_listener(self, listener: ResourceUpdatedListener) -> None:
        if callable(listener):
            self._update_listeners.append(listener)

    def register(
        self,
        func: SyncOrAsyncCallable | None = None,
        *,
        uri: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str = "text/plain",
    ) -> Callable[[SyncOrAsyncCallable], SyncOrAsyncCallable] | SyncOrAsyncCallable:
        if func is None:
            return lambda callback: self.register(
                callback,
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
            )

        manager = get_current_registry_manager()
        if manager is not None and manager.resource_registry is not self:
            return manager.resource_registry.register(
                func,
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
            )

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

    def get(self, uri: str) -> ResourceDefinition | None:
        return self._resources.get(uri)

    def get_resource(self, uri: str) -> ResourceDefinition | None:
        return self.get(uri)

    def definitions(self) -> dict[str, ResourceDefinition]:
        return dict(self._resources)

    def import_resources(self, resources: dict[str, ResourceDefinition]) -> None:
        self._resources.update(resources)

    def get_resources(self) -> dict[str, ResourceDefinition]:
        return dict(self._resources)

    def list_resources(self) -> list[dict[str, Any]]:
        return self.list_payload()

    def list_payload(self) -> list[dict[str, Any]]:
        return [resource.to_mcp_payload() for resource in self._resources.values()]

    def notify_updated(self, uri: str) -> None:
        if uri not in self._resources:
            return
        _notify_update_listeners(self._update_listeners, uri)


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

_CURRENT_REGISTRY_MANAGER: ContextVar[RegistryManager | None] = ContextVar(
    "current_registry_manager",
    default=None,
)


def get_registry_manager(app: Any) -> RegistryManager:
    if not hasattr(app.state, "registry_manager"):
        manager = RegistryManager()
        manager.copy_from_global_registries(tool_registry, prompt_registry, resource_registry)
        app.state.registry_manager = manager
    return cast(RegistryManager, app.state.registry_manager)


def get_current_registry_manager() -> RegistryManager | None:
    return _CURRENT_REGISTRY_MANAGER.get()


def set_current_registry_manager(manager: RegistryManager | None) -> None:
    _CURRENT_REGISTRY_MANAGER.set(manager)


__all__ = [
    "AsyncToolFunction",
    "ListChangedListener",
    "PromptDefinition",
    "PromptRegistry",
    "RegistryManager",
    "ResourceDefinition",
    "ResourceRegistry",
    "ResourceUpdatedListener",
    "SyncOrAsyncCallable",
    "SyncToolFunction",
    "ToolDefinition",
    "ToolExecutionConfig",
    "ToolFunction",
    "ToolRegistry",
    "dump_value",
    "get_current_registry_manager",
    "get_registry_manager",
    "prompt_registry",
    "resource_registry",
    "set_current_registry_manager",
    "tool_registry",
]
