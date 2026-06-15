"""Tests for prompt and resource declaration metadata."""

from pymcp.registry import PromptRegistry, ResourceRegistry


def test_prompt_registry_emits_title_and_icons():
    registry = PromptRegistry()

    @registry.register(
        title="Greeting Prompt",
        icons=[{"src": "https://example.com/prompt.svg", "theme": "light"}],
    )
    def greeting(name: str) -> str:
        return f"Hello, {name}!"

    payload = registry.list_payload()[0]
    assert payload["title"] == "Greeting Prompt"
    assert payload["icons"][0]["theme"] == "light"


def test_resource_registry_emits_extended_metadata():
    registry = ResourceRegistry()

    @registry.register(
        uri="test://resource",
        name="resource",
        title="Resource Title",
        icons=[{"src": "https://example.com/resource.svg", "theme": "dark"}],
        annotations={"priority": 0.5},
        size=42,
    )
    def resource() -> str:
        return "payload"

    @registry.register_template(
        uri_template="test://items/{id}",
        name="items",
        title="Item Template",
        icons=[{"src": "https://example.com/template.svg"}],
        annotations={"audience": ["user"]},
    )
    def item(id: str) -> str:
        return id

    resource_payload = registry.list_payload()[0]
    assert resource_payload["title"] == "Resource Title"
    assert resource_payload["icons"][0]["theme"] == "dark"
    assert resource_payload["annotations"]["priority"] == 0.5
    assert resource_payload["size"] == 42

    template_payload = registry.list_template_payload()[0]
    assert template_payload["title"] == "Item Template"
    assert template_payload["icons"][0]["src"] == "https://example.com/template.svg"
    assert template_payload["annotations"]["audience"] == ["user"]
