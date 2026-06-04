import pytest

from pymcp.protocol.payload import get_payload_factory
from pymcp.protocol.validate import validate_jsonrpc_request
from pymcp.registries.registry import PromptRegistry, ResourceRegistry, ToolRegistry
from pymcp.runtime.limits import RuntimeLimits
from pymcp.security.authn import Principal
from pymcp.security.authz import AuthorizationError, AuthzRequest
from pymcp.security.configured import RuleBasedAuthorizer


def test_get_payload_factory_negotiates_latest_supported_version():
    factory = get_payload_factory(None)

    assert factory.protocol_version == "2025-11-25"


def test_get_payload_factory_rejects_unsupported_version():
    with pytest.raises(ValueError, match="Unsupported protocolVersion"):
        get_payload_factory("1999-01-01")


def test_validate_jsonrpc_request_rejects_scalar_params():
    ok, error = validate_jsonrpc_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": "oops",
        }
    )

    assert ok is False
    assert error == "Params must be an object or array"


def test_registry_clear_notifies_listeners():
    tool_events: list[str] = []
    prompt_events: list[str] = []
    resource_events: list[str] = []

    tool_registry = ToolRegistry()
    prompt_registry = PromptRegistry()
    resource_registry = ResourceRegistry()

    tool_registry.add_listener(lambda: tool_events.append("changed"))
    prompt_registry.add_listener(lambda: prompt_events.append("changed"))
    resource_registry.add_listener(lambda: resource_events.append("changed"))

    tool_registry.register(lambda: None, name="tool-one")
    prompt_registry.register(lambda: [], name="prompt-one")
    resource_registry.register(lambda: "value", uri="file:///resource", name="resource-one")

    tool_events.clear()
    prompt_events.clear()
    resource_events.clear()

    tool_registry.clear()
    prompt_registry.clear()
    resource_registry.clear()

    assert tool_events == ["changed"]
    assert prompt_events == ["changed"]
    assert resource_events == ["changed"]


def test_runtime_limits_ignore_non_positive_env_overrides(monkeypatch):
    monkeypatch.setenv("PYMCP_SESSION_OUTBOUND_QUEUE_MAXSIZE", "0")
    monkeypatch.setenv("PYMCP_MAX_REQUEST_BYTES", "-1")
    monkeypatch.setenv("PYMCP_TOOL_MAX_OUTPUT_BYTES", "0")
    monkeypatch.setenv("PYMCP_TOOL_DEFAULT_TIMEOUT_MS", "-5")

    limits = RuntimeLimits.from_env()

    assert limits.session_outbound_queue_maxsize == RuntimeLimits().session_outbound_queue_maxsize
    assert limits.max_request_bytes == RuntimeLimits().max_request_bytes
    assert limits.tool_max_output_bytes == RuntimeLimits().tool_max_output_bytes
    assert limits.tool_default_timeout_ms == RuntimeLimits().tool_default_timeout_ms


def test_rule_based_authorizer_rejects_malformed_rule_entries():
    with pytest.raises(ValueError, match="authz.rules entries must be objects"):
        RuleBasedAuthorizer({"rules": ["not-a-rule"]})


def test_rule_based_authorizer_conditionless_rule_matches_anonymous():
    authorizer = RuleBasedAuthorizer(
        {
            "default_effect": "deny",
            "rules": [{"rpc_method": "tools/list", "effect": "allow"}],
        }
    )

    authorizer.authorize(None, AuthzRequest(rpc_method="tools/list"))


def test_rule_based_authorizer_required_scopes_stop_at_first_matching_deny():
    authorizer = RuleBasedAuthorizer(
        {
            "default_effect": "deny",
            "rules": [
                {
                    "rpc_method": "tools/call",
                    "effect": "allow",
                    "allow_scopes": ["tools:read"],
                },
                {
                    "rpc_method": "tools/call",
                    "effect": "deny",
                    "message": "tool calls disabled",
                },
                {
                    "rpc_method": "tools/call",
                    "effect": "allow",
                    "allow_scopes": ["tools:write"],
                },
            ],
        }
    )

    scopes = authorizer.required_scopes_for(
        Principal(subject="alice"),
        AuthzRequest(rpc_method="tools/call"),
    )

    assert scopes == ()


def test_rule_based_authorizer_uses_allow_rule_message_for_missing_scope():
    authorizer = RuleBasedAuthorizer(
        {
            "default_effect": "deny",
            "rules": [
                {
                    "rpc_method": "tools/call",
                    "effect": "allow",
                    "allow_scopes": ["tools:write"],
                    "message": "Tool write scope required",
                }
            ],
        }
    )

    with pytest.raises(AuthorizationError) as exc_info:
        authorizer.authorize(
            Principal(subject="alice", scopes={"tools:read"}),
            AuthzRequest(rpc_method="tools/call"),
        )

    assert str(exc_info.value) == "Tool write scope required"
    assert exc_info.value.required_scopes == ("tools:write",)
