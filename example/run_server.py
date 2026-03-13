import logging

from config import middleware_config
from pymcp import (
    CapabilitySettings,
    ServerSettings,
    create_app,
    prompt_registry,
    resource_registry,
    tool_registry,
)

logging.basicConfig(level=logging.DEBUG)


@tool_registry.register
def addNumbersTool(a: float, b: float) -> str:
    """Adds two numbers 'a' and 'b' and returns their sum."""
    return f"Sum of {a} + {b} = {a + b}"


@tool_registry.register
def multiplyNumbersTool(a: float, b: float) -> str:
    """Multiplies two numbers 'a' and 'b' and returns their product."""
    return f"Product of {a} * {b} = {a * b}"


@tool_registry.register
def greetTool(name: str) -> str:
    """Greets a person by their name."""
    return f"Hello, {name}! Nice to meet you!"


@tool_registry.register
def calculateAreaTool(length: float, width: float) -> str:
    """Calculates the area of a rectangle given length and width."""
    area = length * width
    return f"Area of rectangle with length {length} and width {width} = {area}"


@tool_registry.register
def promptEchoTool(prompt: str) -> str:
    """Echoes back the prompt provided, with input validation."""
    if not prompt or "crash" in prompt.lower():
        return "Invalid input. Please try again."
    return f"You said: {prompt}"


@prompt_registry.register(description="Prompt template for release notes.")
def releaseNotesPrompt(service: str) -> str:
    return f"Draft a short release note for the {service} service."


@resource_registry.register(
    uri="memo://welcome",
    name="welcome_memo",
    description="Plain text welcome memo for clients.",
)
def welcomeMemo() -> str:
    return "Welcome to py-mcp. Use tools for actions and resources for read-only context."


if __name__ == "__main__":
    import uvicorn

    app = create_app(
        middleware_config=middleware_config,
        server_settings=ServerSettings(
            name="example-server",
            version="0.2.0",
            capabilities=CapabilitySettings(
                advertise_empty_prompts=False,
                advertise_empty_resources=False,
            ),
        ),
    )
    uvicorn.run(app, host="0.0.0.0", port=8088)
