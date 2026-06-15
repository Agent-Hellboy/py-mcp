"""MCP server fixture exercised by the official conformance test suite.

The official suite (``modelcontextprotocol/conformance``) drives a fixed set of
named tools, resources, and prompts and diffs the responses against golden
payloads.  This module registers exactly those fixtures and wires the
interactive ones (sampling, elicitation, logging, progress) to pymcp's existing
runtime helpers.
"""

from __future__ import annotations

import asyncio
import base64
import struct

from pymcp import (
    CapabilitySettings,
    ServerSettings,
    create_app,
    prompt_registry,
    resource_registry,
    tool_registry,
)
from pymcp.runtime.context import RequestContext
from pymcp.session.elicitation import request_elicitation
from pymcp.session.notifications import send_log_message
from pymcp.session.sampling import request_sampling

# 1x1 red pixel PNG.
_RED_PIXEL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _minimal_wav() -> str:
    """Return base64 of a tiny but valid 8-bit mono PCM WAV file."""

    sample_rate = 8000
    samples = b"\x80" * 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(samples),
        b"WAVE",
        b"fmt ",
        16,
        1,  # PCM
        1,  # mono
        sample_rate,
        sample_rate,  # byte rate
        1,  # block align
        8,  # bits per sample
        b"data",
        len(samples),
    )
    return base64.b64encode(header + samples).decode("ascii")


_WAV_AUDIO = _minimal_wav()


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@tool_registry.register(name="test_simple_text", title="Simple text")
def test_simple_text() -> dict:
    """Return a simple text content block."""
    return {"content": [{"type": "text", "text": "This is a simple text response for testing."}]}


@tool_registry.register(name="test_image_content", title="Image content")
def test_image_content() -> dict:
    """Return an image content block."""
    return {"content": [{"type": "image", "data": _RED_PIXEL_PNG, "mimeType": "image/png"}]}


@tool_registry.register(name="test_audio_content", title="Audio content")
def test_audio_content() -> dict:
    """Return an audio content block."""
    return {"content": [{"type": "audio", "data": _WAV_AUDIO, "mimeType": "audio/wav"}]}


@tool_registry.register(name="test_embedded_resource", title="Embedded resource")
def test_embedded_resource() -> dict:
    """Return an embedded resource content block."""
    return {
        "content": [
            {
                "type": "resource",
                "resource": {
                    "uri": "test://embedded-resource",
                    "mimeType": "text/plain",
                    "text": "This is an embedded resource content.",
                },
            }
        ]
    }


@tool_registry.register(name="test_multiple_content_types", title="Mixed content")
def test_multiple_content_types() -> dict:
    """Return mixed text, image, and resource content."""
    return {
        "content": [
            {"type": "text", "text": "Multiple content types test:"},
            {"type": "image", "data": _RED_PIXEL_PNG, "mimeType": "image/png"},
            {
                "type": "resource",
                "resource": {
                    "uri": "test://mixed-content-resource",
                    "mimeType": "application/json",
                    "text": '{"test":"data","value":123}',
                },
            },
        ]
    }


@tool_registry.register(name="test_error_handling", title="Error handling")
def test_error_handling() -> dict:
    """Return a tool error result."""
    return {
        "isError": True,
        "content": [{"type": "text", "text": "This tool intentionally returns an error for testing"}],
    }


@tool_registry.register(name="test_tool_with_logging", title="Tool with logging")
async def test_tool_with_logging(request_context: RequestContext) -> dict:
    """Emit log notifications during execution."""
    app = request_context.app
    session_id = request_context.session_id
    for message in ("Tool execution started", "Tool processing data", "Tool execution completed"):
        await send_log_message(app, session_id, "info", logger="test_tool_with_logging", data=message)
    return {"content": [{"type": "text", "text": "Tool with logging completed"}]}


@tool_registry.register(name="test_tool_with_progress", title="Tool with progress")
async def test_tool_with_progress(request_context: RequestContext) -> dict:
    """Send progress notifications during execution."""
    if request_context.progress_token is not None:
        await request_context.report_progress(0, 100)
        await asyncio.sleep(0.05)
        await request_context.report_progress(50, 100)
        await asyncio.sleep(0.05)
        await request_context.report_progress(100, 100)
        # Let the final progress notification flush on the SSE stream before the
        # tool result is returned on the POST channel (separate, unordered).
        await asyncio.sleep(0.05)
    return {"content": [{"type": "text", "text": "Tool with progress completed"}]}


@tool_registry.register(name="test_sampling", title="Sampling")
async def test_sampling(prompt: str, request_context: RequestContext) -> dict:
    """Request LLM sampling from the client."""
    result = await request_sampling(
        request_context.app,
        request_context.session_id,
        {
            "messages": [{"role": "user", "content": {"type": "text", "text": prompt}}],
            "maxTokens": 100,
        },
    )
    content = result.get("content") if isinstance(result, dict) else None
    text = content.get("text") if isinstance(content, dict) else ""
    return {"content": [{"type": "text", "text": f"LLM response: {text}"}]}


@tool_registry.register(name="test_elicitation", title="Elicitation")
async def test_elicitation(message: str, request_context: RequestContext) -> dict:
    """Request user input from the client."""
    action, content = await request_elicitation(
        request_context.app,
        request_context.session_id,
        {
            "message": message,
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "User's response"},
                    "email": {"type": "string", "description": "User's email address"},
                },
                "required": ["username", "email"],
            },
        },
    )
    return {"content": [{"type": "text", "text": f"Elicitation completed: action={action}, content={content}"}]}


@tool_registry.register(name="test_elicitation_sep1034_defaults", title="Elicitation defaults")
async def test_elicitation_sep1034_defaults(request_context: RequestContext) -> dict:
    """Request elicitation with schema default values."""
    action, content = await request_elicitation(
        request_context.app,
        request_context.session_id,
        {
            "message": "Please provide your details.",
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "default": "John Doe"},
                    "age": {"type": "integer", "default": 30},
                    "score": {"type": "number", "default": 95.5},
                    "status": {
                        "type": "string",
                        "enum": ["active", "inactive", "pending"],
                        "default": "active",
                    },
                    "verified": {"type": "boolean", "default": True},
                },
            },
        },
    )
    return {"content": [{"type": "text", "text": f"Elicitation completed: action={action}, content={content}"}]}


@tool_registry.register(name="test_elicitation_sep1330_enums", title="Elicitation enums")
async def test_elicitation_sep1330_enums(request_context: RequestContext) -> dict:
    """Request elicitation exercising all enum variants."""
    action, content = await request_elicitation(
        request_context.app,
        request_context.session_id,
        {
            "message": "Please choose options.",
            "requestedSchema": {
                "type": "object",
                "properties": {
                    "untitledSingle": {"type": "string", "enum": ["option1", "option2", "option3"]},
                    "titledSingle": {
                        "type": "string",
                        "oneOf": [
                            {"const": "value1", "title": "First Option"},
                            {"const": "value2", "title": "Second Option"},
                        ],
                    },
                    "legacyEnum": {
                        "type": "string",
                        "enum": ["opt1", "opt2", "opt3"],
                        "enumNames": ["Option One", "Option Two", "Option Three"],
                    },
                    "untitledMulti": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["option1", "option2", "option3"]},
                    },
                    "titledMulti": {
                        "type": "array",
                        "items": {
                            "anyOf": [
                                {"const": "value1", "title": "First Choice"},
                                {"const": "value2", "title": "Second Choice"},
                            ],
                        },
                    },
                },
            },
        },
    )
    return {"content": [{"type": "text", "text": f"Elicitation completed: action={action}, content={content}"}]}


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #
@resource_registry.register(
    uri="test://static-text",
    name="static_text",
    description="Static text resource.",
    mime_type="text/plain",
)
def static_text() -> dict:
    return {
        "contents": [
            {
                "uri": "test://static-text",
                "mimeType": "text/plain",
                "text": "This is the content of the static text resource.",
            }
        ]
    }


@resource_registry.register(
    uri="test://static-binary",
    name="static_binary",
    description="Static binary resource.",
    mime_type="image/png",
)
def static_binary() -> dict:
    return {
        "contents": [
            {
                "uri": "test://static-binary",
                "mimeType": "image/png",
                "blob": _RED_PIXEL_PNG,
            }
        ]
    }


@resource_registry.register(
    uri="test://watched-resource",
    name="watched_resource",
    description="Resource used for subscribe/unsubscribe scenarios.",
)
def watched_resource() -> str:
    return "watched"


@resource_registry.register_template(
    uri_template="test://template/{id}/data",
    name="template_data",
    description="Parameterized conformance resource.",
)
def template_data(id: str) -> dict:
    return {
        "contents": [
            {
                "uri": f"test://template/{id}/data",
                "mimeType": "application/json",
                "text": f'{{"id":"{id}","templateTest":true,"data":"Data for ID: {id}"}}',
            }
        ]
    }


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #
@prompt_registry.register(name="test_simple_prompt", description="Simple prompt for testing.")
def test_simple_prompt() -> dict:
    return {
        "messages": [
            {"role": "user", "content": {"type": "text", "text": "This is a simple prompt for testing."}}
        ]
    }


@prompt_registry.register(name="test_prompt_with_arguments", description="Prompt with arguments.")
def test_prompt_with_arguments(arg1: str, arg2: str) -> dict:
    return {
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": f"Prompt with arguments: arg1='{arg1}', arg2='{arg2}'"},
            }
        ]
    }


@prompt_registry.register(name="test_prompt_with_embedded_resource", description="Prompt with embedded resource.")
def test_prompt_with_embedded_resource(resourceUri: str) -> dict:
    return {
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "resource",
                    "resource": {
                        "uri": resourceUri,
                        "mimeType": "text/plain",
                        "text": "Embedded resource content for testing.",
                    },
                },
            },
            {"role": "user", "content": {"type": "text", "text": "Please process the embedded resource above."}},
        ]
    }


@prompt_registry.register(name="test_prompt_with_image", description="Prompt with image.")
def test_prompt_with_image() -> dict:
    return {
        "messages": [
            {"role": "user", "content": {"type": "image", "data": _RED_PIXEL_PNG, "mimeType": "image/png"}},
            {"role": "user", "content": {"type": "text", "text": "Please analyze the image above."}},
        ]
    }


app = create_app(
    middleware_config=None,
    server_settings=ServerSettings(
        name="pymcp-kit-conformance",
        version="0.1.0",
        capabilities=CapabilitySettings(
            prompts_list_changed=True,
            resources_list_changed=True,
            resources_subscribe=True,
            tools_list_changed=True,
            logging_enabled=True,
            completions_enabled=True,
            tasks_enabled=True,
        ),
    ),
)
