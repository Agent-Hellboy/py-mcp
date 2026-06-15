"""Tests for progress notifications surfaced to tools via RequestContext.

Tools must be registered before ``create_app`` since the app copies the global
registries at creation time.
"""

import json

import pytest

from pymcp import create_app, tool_registry
from pymcp.runtime.context import AppContext, RequestContext, SessionContext
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.session import get_session_manager
from tests.support import initialize_ready_session

pytestmark = pytest.mark.anyio


def _drain(queue) -> list[dict]:
    messages: list[dict] = []
    while not queue.empty():
        messages.append(json.loads(queue.get_nowait()))
    return messages


async def _ready_session_with_stream(app):
    session = await initialize_ready_session(app)
    await get_session_manager(app).note_stream_open(session.session_id, stream_id="stream-1")
    return session


async def _call_tool(app, session, name, *, meta=None):
    params = {"name": name, "arguments": {}}
    if meta is not None:
        params["_meta"] = meta
    await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": params},
        app=app,
        direct_response=True,
    )


async def test_tools_call_emits_progress_for_request_token():
    @tool_registry.register(name="progress_tool")
    async def progress_tool(request_context: RequestContext) -> dict:
        await request_context.report_progress(0, 100)
        await request_context.report_progress(100, 100, message="done")
        return {"content": [{"type": "text", "text": "ok"}]}

    app = create_app(middleware_config=None)
    session = await _ready_session_with_stream(app)
    await _call_tool(app, session, "progress_tool", meta={"progressToken": "pt-x"})

    progress = [m for m in _drain(session.queue) if m.get("method") == "notifications/progress"]
    assert len(progress) == 2
    assert progress[0]["params"] == {"progressToken": "pt-x", "progress": 0, "total": 100}
    assert progress[1]["params"]["progress"] == 100
    assert progress[1]["params"]["message"] == "done"


async def test_tools_call_without_token_sends_no_progress():
    @tool_registry.register(name="quiet_tool")
    async def quiet_tool(request_context: RequestContext) -> dict:
        assert request_context.progress_token is None
        await request_context.report_progress(50, 100)
        return {"content": [{"type": "text", "text": "ok"}]}

    app = create_app(middleware_config=None)
    session = await _ready_session_with_stream(app)
    await _call_tool(app, session, "quiet_tool")

    progress = [m for m in _drain(session.queue) if m.get("method") == "notifications/progress"]
    assert progress == []


async def test_tools_call_preserves_integer_progress_token():
    @tool_registry.register(name="int_token_tool")
    async def int_token_tool(request_context: RequestContext) -> dict:
        await request_context.report_progress(1, 2)
        return {"content": [{"type": "text", "text": "ok"}]}

    app = create_app(middleware_config=None)
    session = await _ready_session_with_stream(app)
    await _call_tool(app, session, "int_token_tool", meta={"progressToken": 7})

    progress = [m for m in _drain(session.queue) if m.get("method") == "notifications/progress"]
    assert len(progress) == 1
    assert progress[0]["params"]["progressToken"] == 7


async def test_request_context_report_progress_noop_without_token():
    app = create_app(middleware_config=None)
    session = await _ready_session_with_stream(app)
    ctx = RequestContext(
        app_context=AppContext(app),
        session_context=SessionContext(session.session_id),
    )

    assert ctx.app is app
    assert ctx.session_id == session.session_id

    await ctx.report_progress(10, 100)
    assert _drain(session.queue) == []


async def test_request_context_report_progress_noop_for_missing_session():
    app = create_app(middleware_config=None)
    ctx = RequestContext(
        app_context=AppContext(app),
        session_context=SessionContext("does-not-exist"),
        progress_token="pt-y",
    )

    # Should not raise even though the session cannot be found.
    await ctx.report_progress(10, 100)
