import pytest
from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.protocol.meta import (
    MetaValidationError,
    attach_meta,
    extract_request_meta,
    split_result_meta,
    validate_meta_value,
    validate_request_meta,
)
from pymcp.protocol.errors import MCPErrorCode
from pymcp.registry import tool_registry


def _headers(session_id=None, *, accept="application/json, text/event-stream"):
    headers = {"Accept": accept}
    if session_id:
        headers["MCP-Session-Id"] = session_id
    return headers


def _initialize_session(client: TestClient):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
    }
    response = client.post("/mcp", json=payload, headers=_headers())
    assert response.status_code == 200
    return response.headers["MCP-Session-Id"]


def test_validate_meta_value_rejects_non_object():
    with pytest.raises(MetaValidationError, match="must be an object"):
        validate_meta_value("bad", location="_meta")


def test_validate_request_meta_accepts_top_level_and_params():
    validate_request_meta(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "_meta": {"progressToken": "pt-1"},
            "params": {"name": "demo", "_meta": {"client": "test"}},
        }
    )


def test_validate_request_meta_rejects_invalid_params_meta():
    with pytest.raises(MetaValidationError, match="params._meta"):
        validate_request_meta(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "demo", "_meta": []},
            }
        )


def test_extract_request_meta_merges_top_level_and_params():
    merged = extract_request_meta(
        {
            "_meta": {"progressToken": "pt-1"},
            "params": {"_meta": {"client": "test"}},
        }
    )
    assert merged == {"progressToken": "pt-1", "client": "test"}


def test_attach_meta_merges_existing_envelope_meta():
    payload = attach_meta({"jsonrpc": "2.0", "id": 1, "result": {}}, {"a": 1})
    payload = attach_meta(payload, {"b": 2})
    assert payload["_meta"] == {"a": 1, "b": 2}


def test_split_result_meta_lifts_meta_from_result_body():
    body, meta = split_result_meta(
        {
            "content": [{"type": "text", "text": "ok"}],
            "_meta": {"progressToken": "pt-2"},
        }
    )
    assert "_meta" not in body
    assert meta == {"progressToken": "pt-2"}


def test_dispatch_rejects_invalid_request_meta():
    client = TestClient(create_app())
    session_id = _initialize_session(client)
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(session_id),
    )

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "_meta": "not-an-object",
        },
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error"]["code"] == MCPErrorCode.INVALID_PARAMS
    assert "_meta must be an object" in body["error"]["message"]


def test_tools_call_lifts_result_meta_to_response_envelope():
    @tool_registry.register
    def meta_tool() -> dict[str, object]:
        return {
            "content": [{"type": "text", "text": "done"}],
            "_meta": {"progressToken": "pt-tool"},
        }

    client = TestClient(create_app())
    session_id = _initialize_session(client)
    client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=_headers(session_id),
    )

    response = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "meta_tool", "arguments": {}},
        },
        headers=_headers(session_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["content"][0]["text"] == "done"
    assert "_meta" not in body["result"]
    assert body["_meta"] == {"progressToken": "pt-tool"}
