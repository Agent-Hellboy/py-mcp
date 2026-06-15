"""Application settings for PyMCP Kit."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)


JSONObject = dict[str, Any]


@dataclass(slots=True)
class CapabilitySettings:
    # -- server capability knobs (advertised in initialize response) ------
    tools_list_changed: bool = False
    prompts_list_changed: bool = False
    resources_list_changed: bool = False
    resources_subscribe: bool = True
    advertise_empty_prompts: bool = False
    advertise_empty_resources: bool = False
    logging_enabled: bool = False
    completions_enabled: bool = False
    tasks_enabled: bool = True
    tasks_tool_call: bool = True
    tasks_list: bool = True
    tasks_cancel: bool = True
    list_page_size: int = 50
    experimental_features: dict[str, JSONObject] | None = None

    def __post_init__(self) -> None:
        if self.list_page_size <= 0:
            raise ValueError("list_page_size must be a positive integer")


@dataclass(slots=True)
class ServerSettings:
    name: str = "pymcp-kit"
    version: str = "0.2.0"
    protocol_versions: tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS
    capabilities: CapabilitySettings = field(default_factory=CapabilitySettings)
    title: str | None = None
    description: str | None = None
    website_url: str | None = None
    icons: list[JSONObject] | None = None

    def __post_init__(self) -> None:
        if not self.protocol_versions:
            raise ValueError(
                "ServerSettings.protocol_versions cannot be empty; "
                "at least one supported version is required"
            )


__all__ = [
    "CapabilitySettings",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "ServerSettings",
]
