"""Capability helpers."""

from __future__ import annotations

from typing import Any

from .registries.registry import PromptRegistry, ResourceRegistry, ToolRegistry
from .settings import CapabilitySettings


def build_capabilities(
    settings: CapabilitySettings,
    tools: ToolRegistry,
    prompts: PromptRegistry,
    resources: ResourceRegistry,
) -> dict[str, Any]:
    capabilities: dict[str, Any] = {
        "tools": {"listChanged": settings.tools_list_changed},
    }

    if prompts.get_prompts() or settings.advertise_empty_prompts:
        capabilities["prompts"] = {"listChanged": settings.prompts_list_changed}

    if resources.get_resources() or settings.advertise_empty_resources:
        capabilities["resources"] = {
            "listChanged": settings.resources_list_changed,
            "subscribe": settings.resources_subscribe,
        }

    return capabilities


__all__ = ["build_capabilities"]
