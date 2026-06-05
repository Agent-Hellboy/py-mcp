"""Completion resolution helpers for prompts and resource templates."""

from __future__ import annotations

from typing import Any

from ...protocol.errors import MCPErrorCode
from ...registries.registry import PromptDefinition, RegistryManager
from ...util.completion import (
    build_completion_result,
    completion_candidates_from_argument,
    extract_template_variables,
)


class CompletionResolutionError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _template_variable_completions(template: Any, variable: str) -> list[str]:
    variables = getattr(template, "variable_completions", None)
    if isinstance(variables, dict):
        values = variables.get(variable)
        if isinstance(values, list):
            return [str(value) for value in values]

    metadata = getattr(template, "variables", None)
    if isinstance(metadata, dict):
        variable_meta = metadata.get(variable)
        if isinstance(variable_meta, dict):
            return completion_candidates_from_argument(variable_meta)

    return []


def resolve_prompt_completion(
    *,
    registry_manager: RegistryManager,
    prompt_name: str,
    argument_name: str,
    argument_value: str,
) -> dict[str, object]:
    prompt = registry_manager.get_prompt_registry().get(prompt_name)
    if prompt is None:
        raise CompletionResolutionError(MCPErrorCode.INVALID_PARAMS, f"Unknown prompt: {prompt_name}")

    candidates = _prompt_completion_candidates(prompt, argument_name)
    if not candidates:
        return build_completion_result([], prefix=argument_value)
    return build_completion_result(candidates, prefix=argument_value)


def resolve_resource_completion(
    *,
    registry_manager: RegistryManager,
    uri_template: str,
    argument_name: str,
    argument_value: str,
) -> dict[str, object]:
    resource_registry = registry_manager.get_resource_registry()
    get_template = getattr(resource_registry, "get_template", None)
    if not callable(get_template):
        raise CompletionResolutionError(
            MCPErrorCode.METHOD_NOT_FOUND,
            "Resource template completions are not supported",
        )

    template = get_template(uri_template)
    if template is None:
        raise CompletionResolutionError(
            MCPErrorCode.RESOURCE_NOT_FOUND,
            f"Unknown resource template: {uri_template}",
        )

    variables = extract_template_variables(uri_template)
    if argument_name not in variables:
        raise CompletionResolutionError(
            MCPErrorCode.INVALID_PARAMS,
            f"Unknown template argument: {argument_name}",
        )

    candidates = _template_variable_completions(template, argument_name)
    return build_completion_result(candidates, prefix=argument_value)


def _prompt_completion_candidates(prompt: PromptDefinition, argument_name: str) -> list[str]:
    for argument in prompt.arguments:
        if argument.get("name") != argument_name:
            continue
        return completion_candidates_from_argument(argument)
    return []


__all__ = [
    "CompletionResolutionError",
    "resolve_prompt_completion",
    "resolve_resource_completion",
]
