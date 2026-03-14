import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from pymcp import create_app
from pymcp.session import get_session_manager, request_elicitation


pytestmark = pytest.mark.anyio


async def test_request_elicitation_queues_request_and_resolves_response():
    app = create_app(middleware_config=None)
    session = get_session_manager(app).create_session()

    task = asyncio.create_task(
        request_elicitation(
            app,
            session.session_id,
            {"message": "Provide additional details."},
        )
    )

    outbound = json.loads(await asyncio.wait_for(session.queue.get(), timeout=1.0))
    rpc_id = outbound["id"]
    assert outbound["method"] == "elicitation/create"
    assert outbound["params"]["mode"] == "form"

    get_session_manager(app).resolve_elicitation_response(
        session.session_id,
        rpc_id,
        {"jsonrpc": "2.0", "id": rpc_id, "result": {"action": "accept"}},
    )

    returned_id, response = await asyncio.wait_for(task, timeout=1.0)
    assert returned_id == rpc_id
    assert response["result"]["action"] == "accept"


async def test_streamable_http_response_only_resolves_pending_elicitation():
    app = create_app(middleware_config=None)
    client = TestClient(app)
    manager = get_session_manager(app)
    session = manager.create_session()

    future = asyncio.get_running_loop().create_future()
    manager.register_elicitation_future(session.session_id, "elic-1", future)

    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "elic-1", "result": {"action": "accept"}},
        headers={
            "Accept": "application/json",
            "MCP-Session-Id": session.session_id,
        },
    )

    assert response.status_code == 202
    assert future.result()["result"]["action"] == "accept"
