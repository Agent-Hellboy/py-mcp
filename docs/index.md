# PyMCP Kit

<div class="hero" markdown>

Capability-first MCP server tooling for FastAPI. `pymcp-kit` keeps the built-in transport surface small, exposes app-scoped registries, and ships the MCP features you typically need first: tools, prompts, resources, roots, task-aware execution, and optional auth hooks.

<div class="hero-actions" markdown>
[Get Started](getting-started.md){ .md-button .md-button--primary }
[Runtime Surface](runtime-surface.md){ .md-button }
</div>

</div>

<div class="pymcp-grid" markdown>

<div class="pymcp-card" markdown>

### Small transport surface

Use Streamable HTTP at `/mcp` for networked clients and stdio for subprocess-based MCP hosts.

</div>

<div class="pymcp-card" markdown>

### App-scoped registries

Register tools, prompts, and resources globally for simple setups, then let `create_app()` snapshot them into an isolated app runtime.

</div>

<div class="pymcp-card" markdown>

### Tasks that stay useful

Opt tools into task execution, emit progress, request user input, support cancellation, and return results without flattening structured payloads.

</div>

<div class="pymcp-card" markdown>

### Security when you need it

Add bearer-token authentication and rule-based authorization without turning the package into a large framework.

</div>

</div>

## Quick Install

```bash
pip install pymcp-kit
```

## What Ships Today

- Streamable HTTP mounted at `/mcp`
- Stdio transport through `run_stdio_server(app)`
- Tool, prompt, and resource registries
- Roots and resource subscriptions
- Task-aware tool execution with progress, cancellation, and elicitation
- Optional authentication and authorization hooks

## Main Protocol Surface

- Lifecycle: `initialize`, `ping`, `notifications/initialized`, `notifications/cancelled`
- Tools: `tools/list`, `tools/call`
- Prompts: `prompts/list`, `prompts/get`
- Resources: `resources/list`, `resources/read`, `resources/subscribe`, `resources/unsubscribe`
- Roots: `roots/list`
- Tasks: `tasks/list`, `tasks/get`, `tasks/cancel`, `tasks/result`

## Read Next

- [Getting Started](getting-started.md): installation, the basic app factory flow, and the built-in transports.
- [Tasks](tasks.md): task-aware tool execution, progress, cancellation, and result polling.
- [Security](security.md): bearer tokens, rule-based authorization, and capability filtering.
- [Docs Deployment](deployment.md): how this site is built and published with GitHub Pages.
