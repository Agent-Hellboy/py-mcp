import pytest

from pymcp.registry import prompt_registry, resource_registry, tool_registry


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _register_sample_capabilities():
    """Register sample tools, prompts, and resources."""

    @tool_registry.register
    def add_numbers_tool(a: float, b: float) -> str:
        """Adds two numbers."""
        return f"Sum of {a} + {b} = {a + b}"

    @tool_registry.register
    async def greet_tool(name: str) -> str:
        """Greets a user."""
        return f"Hello, {name}"

    @tool_registry.register
    def prompt_echo_tool(prompt: str) -> str:
        """Echoes the provided prompt."""
        return f"You said: {prompt}"

    @prompt_registry.register(description="Summarize a support question for triage.")
    def summarize_prompt(topic: str) -> str:
        return f"Summarize the support issue about {topic} in three bullets."

    @resource_registry.register(
        uri="memo://release-plan",
        name="release_plan",
        description="Release checklist snapshot.",
        mime_type="text/markdown",
    )
    def release_plan() -> str:
        return "# Release Plan\n- add prompts\n- add resources\n"


@pytest.fixture
def sample_capabilities():
    """Register sample tools, prompts, and resources for tests that need them."""
    _register_sample_capabilities()


@pytest.fixture(autouse=True)
def reset_registries():
    tool_registry.clear()
    prompt_registry.clear()
    resource_registry.clear()
    yield
    tool_registry.clear()
    prompt_registry.clear()
    resource_registry.clear()
