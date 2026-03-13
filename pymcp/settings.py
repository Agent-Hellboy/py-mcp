"""Application settings for PyMCP Kit."""

from __future__ import annotations

from dataclasses import dataclass, field


SUPPORTED_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)


@dataclass(slots=True)
class CapabilitySettings:
    tools_list_changed: bool = False
    prompts_list_changed: bool = False
    resources_list_changed: bool = False
    resources_subscribe: bool = False
    advertise_empty_prompts: bool = False
    advertise_empty_resources: bool = False


@dataclass(slots=True)
class ServerSettings:
    name: str = "pymcp-kit"
    version: str = "0.1.0"
    protocol_versions: tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS
    capabilities: CapabilitySettings = field(default_factory=CapabilitySettings)

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
