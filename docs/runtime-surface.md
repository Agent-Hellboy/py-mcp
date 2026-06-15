# Runtime Surface

`pymcp-kit` keeps the built-in surface intentionally narrow. This page is the quickest way to see what the package exposes at runtime and what capability toggles affect the MCP handshake.

## Supported Protocol Versions

`ServerSettings.protocol_versions` currently defaults to:

- `2025-11-25`
- `2025-06-18`
- `2025-03-26`
- `2024-11-05`

## Built-In HTTP Endpoints

- `GET /`: basic server metadata
- `POST /mcp`: Streamable HTTP MCP endpoint
- `GET /mcp`: transport support endpoint for streamable sessions
- `DELETE /mcp`: session termination endpoint for streamable sessions

## Implemented MCP Methods

### Lifecycle

- `initialize`
- `ping`
- `notifications/initialized`
- `notifications/cancelled`

### Tools

- `tools/list`
- `tools/call`

Tool registration supports optional declaration metadata:

- `title`
- `outputSchema`
- `annotations` (`readOnlyHint`, `destructiveHint`, `openWorldHint`, `idempotentHint`)
- `icons`

Tool handlers may return `structuredContent` alongside `content` blocks in `tools/call` results.

```python
from pymcp import tool_registry

@tool_registry.register(
    title="Add numbers",
    output_schema={"type": "object", "properties": {"sum": {"type": "number"}}},
    annotations={"readOnlyHint": True, "destructiveHint": False},
)
def addNumbersTool(a: float, b: float) -> dict:
    total = a + b
    return {
        "content": [{"type": "text", "text": str(total)}],
        "structuredContent": {"sum": total},
    }
```

### Prompts

- `prompts/list`
- `prompts/get`

### Resources

- `resources/list`
- `resources/templates/list`
- `resources/read`
- `resources/subscribe`
- `resources/unsubscribe`
- `notifications/resources/updated`

### Roots (Client Capability)

Roots are a *client* capability. The server can request the client's roots
via the `request_roots_list()` helper (sends `roots/list` to the client).

- `notifications/roots/list_changed` (client -> server notification)

### Completions

- `completion/complete`

Prompt argument completions are resolved from each argument's `schema.enum` or
explicit `completion` list. Resource template variable completions are resolved
from optional `variables` metadata passed to `register_template()`.

```python
@prompt_registry.register(
    arguments=[
        {
            "name": "language",
            "required": True,
            "schema": {"type": "string", "enum": ["python", "javascript", "rust"]},
        }
    ]
)
def languagePrompt(language: str) -> str:
    return language

@resource_registry.register_template(
    uri_template="memo://{topic}",
    variables={"topic": {"completion": ["welcome", "release-notes"]}},
)
def memoTemplate(topic: str) -> str:
    return topic
```

### Tasks

- `tasks/list`
- `tasks/get`
- `tasks/cancel`
- `tasks/result`
- `notifications/tasks/status`
- `notifications/progress`

### Elicitation (Client Capability)

Elicitation is a *client* capability. The server sends `elicitation/create`
to the client via the `request_elicitation()` helper. Both `form` and `url`
modes are supported.

### Sampling (Client Capability)

Sampling is a *client* capability. The server sends `sampling/createMessage`
to the client via the `request_sampling()` helper.

### Logging

- `logging/setLevel`
- `notifications/message` (server -> client log notification via `send_log_message()`)

## Request and Result Metadata (`_meta`)

JSON-RPC requests may carry `_meta` at the top level or under `params`. The runtime validates that each present `_meta` value is an object and merges top-level and params metadata for handlers that need progress tokens or related-task links.

Tool handlers lift `_meta` from a tool result body onto the JSON-RPC response envelope so clients receive metadata alongside the MCP result object. Task result responses use the same envelope-level `_meta` pattern.

## Capability Settings

`CapabilitySettings` controls which fragments appear in `initialize.result.capabilities` and which optional runtime behaviors are enabled.

Per the MCP 2025-11-25 spec, **server** capabilities (advertised in the initialize response) include: tools, prompts, resources, logging, completions, tasks, and experimental. **Client** capabilities (roots, sampling, elicitation) are declared by the client in the initialize request and are NOT part of server capability settings.

| Setting | Default | Effect |
| --- | --- | --- |
| `tools_list_changed` | `False` | Advertise `tools.listChanged` support. |
| `prompts_list_changed` | `False` | Advertise `prompts.listChanged` support. |
| `resources_list_changed` | `False` | Advertise `resources.listChanged` support. |
| `resources_subscribe` | `True` | Advertise and enable resource subscription support. |
| `advertise_empty_prompts` | `False` | Expose a prompts capability even when no prompts are registered. |
| `advertise_empty_resources` | `False` | Expose a resources capability even when no resources are registered. |
| `logging_enabled` | `False` | Advertise `logging` capability. |
| `completions_enabled` | `False` | Advertise `completions` capability and enable `completion/complete` handler. |
| `tasks_enabled` | `True` | Expose task capability fragments and task handlers. |
| `tasks_tool_call` | `True` | Advertise task augmentation for `tools/call`. |
| `tasks_list` | `True` | Advertise the `tasks/list` capability fragment. |
| `tasks_cancel` | `True` | Advertise the `tasks/cancel` capability fragment. |
| `experimental_features` | `None` | Dict of experimental server features to advertise. |

## Server Metadata

By default, `ServerSettings()` uses:

```python
ServerSettings(
    name="pymcp-kit",
    version="0.1.0",
)
```

Those defaults flow into both:

- the HTTP root payload returned from `GET /`
- `initialize.result.serverInfo`

## Current Non-Goals

- SSE and HTTP NDJSON transports are intentionally not bundled
- metrics and tracing are not part of the shipped surface
- the package focuses on a practical MCP server core rather than a full framework stack
