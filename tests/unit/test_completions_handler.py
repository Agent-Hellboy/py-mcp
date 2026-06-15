"""Tests for completion/complete handler."""

import pytest

from pymcp import create_app
from pymcp.registry import prompt_registry, resource_registry
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session.store import get_session_manager
from pymcp.settings import CapabilitySettings, ServerSettings


pytestmark = pytest.mark.anyio


async def _ready_session(app):
    manager = get_session_manager(app)
    session = manager.create_session()
    await manager.mark_initialize_started(session.session_id)
    await manager.mark_initialized(session.session_id)
    return session


async def _complete(app, session_id: str, params: dict, *, request_id: int = 1):
    return await process_jsonrpc_message(
        session_id,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "completion/complete",
            "params": params,
        },
        app=app,
        direct_response=True,
    )


async def test_completions_gated_when_disabled():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=False)
        ),
    )
    session = await _ready_session(app)

    result = await _complete(
        app,
        session.session_id,
        {
            "ref": {"type": "ref/prompt", "name": "test"},
            "argument": {"name": "topic", "value": "wea"},
        },
    )
    assert result.status == 200
    assert result.payload["error"]["code"] == -32601
    assert "completions not supported" in result.payload["error"]["message"]


async def test_prompt_completion_uses_enum_values():
    @prompt_registry.register(
        name="languagePrompt",
        arguments=[
            {
                "name": "language",
                "required": True,
                "schema": {"type": "string", "enum": ["python", "pytorch", "pyside", "java"]},
            }
        ],
    )
    def languagePrompt(language: str) -> str:
        return language

    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await _complete(
        app,
        session.session_id,
        {
            "ref": {"type": "ref/prompt", "name": "languagePrompt"},
            "argument": {"name": "language", "value": "py"},
        },
    )
    completion = result.payload["result"]["completion"]
    assert completion["values"] == ["python", "pytorch", "pyside"]
    assert completion["total"] == 3
    assert completion["hasMore"] is False


async def test_prompt_completion_rejects_unknown_prompt():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await _complete(
        app,
        session.session_id,
        {
            "ref": {"type": "ref/prompt", "name": "missingPrompt"},
            "argument": {"name": "topic", "value": "wea"},
        },
    )
    assert result.payload["error"]["code"] == -32602
    assert "Unknown prompt" in result.payload["error"]["message"]


async def test_resource_template_completion_uses_variable_metadata():
    @resource_registry.register_template(
        uri_template="memo://{topic}",
        name="memo_template",
        variables={
            "topic": {
                "completion": ["welcome", "release-notes", "security"],
            }
        },
    )
    def memoTemplate(topic: str) -> str:
        return topic

    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await _complete(
        app,
        session.session_id,
        {
            "ref": {"type": "ref/resource", "uri": "memo://{topic}"},
            "argument": {"name": "topic", "value": "re"},
        },
    )
    completion = result.payload["result"]["completion"]
    assert completion["values"] == ["release-notes"]
    assert completion["total"] == 1
    assert completion["hasMore"] is False


async def test_completions_rejects_missing_ref():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await _complete(
        app,
        session.session_id,
        {"argument": {"name": "topic", "value": "wea"}},
    )
    assert result.payload["error"]["code"] == -32602


async def test_completions_rejects_missing_argument():
    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(completions_enabled=True)
        ),
    )
    session = await _ready_session(app)

    result = await _complete(
        app,
        session.session_id,
        {"ref": {"type": "ref/prompt", "name": "test"}},
    )
    assert result.payload["error"]["code"] == -32602
