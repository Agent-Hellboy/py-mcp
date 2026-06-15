import pytest

from pymcp import create_app
from pymcp.registry import resource_registry
from pymcp.runtime.dispatch import process_jsonrpc_message
from pymcp.settings import CapabilitySettings, ServerSettings
from pymcp.util.uri_template import match_uri_template
from tests.support import initialize_ready_session


pytestmark = pytest.mark.anyio
def test_match_uri_template_captures_variables():
    assert match_uri_template("note://{topic}", "note://release") == {"topic": "release"}
    assert match_uri_template("file:///{path}", "file:///project/src/main.rs") == {
        "path": "project/src/main.rs",
    }
    assert match_uri_template("note://{topic}", "memo://release") is None


def test_uri_template_rejects_invalid_variable_name():
    with pytest.raises(ValueError, match="Invalid variable name"):
        match_uri_template("note://{topic-name}", "note://release")


def test_resource_template_rejects_handler_signature_mismatch():
    with pytest.raises(ValueError, match="does not match"):

        @resource_registry.register_template(uri_template="note://{topic}")
        def invalid_template_handler(category: str) -> str:
            return category


async def test_resources_templates_list_and_read():
    @resource_registry.register_template(
        uri_template="note://{topic}",
        name="topic_note",
        description="Parameterized note resource.",
    )
    def topic_note(topic: str) -> str:
        return f"Notes for {topic}"

    app = create_app(middleware_config=None)
    session = await initialize_ready_session(app)

    templates = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/templates/list",
        },
        app=app,
        direct_response=True,
    )
    assert templates.payload["result"]["resourceTemplates"] == [
        {
            "uriTemplate": "note://{topic}",
            "name": "topic_note",
            "description": "Parameterized note resource.",
            "mimeType": "text/plain",
        }
    ]

    read = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/read",
            "params": {"uri": "note://release"},
        },
        app=app,
        direct_response=True,
    )
    assert read.payload["result"]["contents"][0]["text"] == "Notes for release"
    assert read.payload["result"]["contents"][0]["uri"] == "note://release"


async def test_template_uri_binding_is_not_overwritten():
    @resource_registry.register_template(uri_template="note://{uri}")
    def uri_note(uri: str) -> str:
        return uri

    app = create_app(middleware_config=None)
    session = await initialize_ready_session(app)
    read = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/read",
            "params": {"uri": "note://release"},
        },
        app=app,
        direct_response=True,
    )
    assert read.payload["result"]["contents"][0]["text"] == "release"


async def test_resources_list_pagination():
    for index in range(3):
        uri = f"memo://item-{index}"

        @resource_registry.register(uri=uri, name=f"item_{index}")
        def item_resource() -> str:
            return "value"

    app = create_app(
        middleware_config=None,
        server_settings=ServerSettings(
            capabilities=CapabilitySettings(list_page_size=2),
        ),
    )
    session = await initialize_ready_session(app)

    first_page = await process_jsonrpc_message(
        session.session_id,
        {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
        app=app,
        direct_response=True,
    )
    assert len(first_page.payload["result"]["resources"]) == 2
    assert first_page.payload["result"]["nextCursor"] == "2"

    second_page = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/list",
            "params": {"cursor": "2"},
        },
        app=app,
        direct_response=True,
    )
    assert len(second_page.payload["result"]["resources"]) == 1
    assert "nextCursor" not in second_page.payload["result"]


async def test_resources_templates_list_rejects_invalid_cursor():
    @resource_registry.register_template(uri_template="note://{topic}", name="topic_note")
    def topic_note(topic: str) -> str:
        return topic

    app = create_app(middleware_config=None)
    session = await initialize_ready_session(app)

    response = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/templates/list",
            "params": {"cursor": "not-a-number"},
        },
        app=app,
        direct_response=True,
    )
    assert response.payload["error"]["code"] == -32602


async def test_template_resource_subscription():
    @resource_registry.register_template(uri_template="note://{topic}", name="topic_note")
    def topic_note(topic: str) -> str:
        return topic

    app = create_app(middleware_config=None)
    session = await initialize_ready_session(app)

    subscribe = await process_jsonrpc_message(
        session.session_id,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "resources/subscribe",
            "params": {"uri": "note://release"},
        },
        app=app,
        direct_response=True,
    )
    assert subscribe.payload["result"]["subscribed"] == ["note://release"]
