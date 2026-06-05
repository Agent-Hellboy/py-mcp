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

### Prompts

- `prompts/list`
- `prompts/get`

### Resources

- `resources/list`
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
