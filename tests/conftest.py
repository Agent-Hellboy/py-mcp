import pytest

from tests.support import register_sample_capabilities


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sample_capabilities():
    """Register sample tools, prompts, and resources for tests that need them."""
    register_sample_capabilities()


@pytest.fixture(autouse=True)
def reset_registries():
    from pymcp.registry import prompt_registry, resource_registry, tool_registry

    tool_registry.clear()
    prompt_registry.clear()
    resource_registry.clear()
    yield
    tool_registry.clear()
    prompt_registry.clear()
    resource_registry.clear()
