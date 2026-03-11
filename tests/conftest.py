import pytest

from pymcp.registry import prompt_registry, resource_registry, tool_registry


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_registries():
    tool_registry.clear()
    prompt_registry.clear()
    resource_registry.clear()
    yield
    tool_registry.clear()
    prompt_registry.clear()
    resource_registry.clear()
