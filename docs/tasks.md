# Tasks

`pymcp-kit` supports task-aware tool execution, result polling, cancellation, and progress reporting. Tasks are enabled by default at the capability level, but each tool still decides whether task augmentation is allowed.

## Opt A Tool Into Tasks

Use `execution.taskSupport` on the tool definition:

- `"optional"`: the tool can run directly or as a task
- `"required"`: the caller must use task augmentation
- `"forbidden"`: the tool only runs as a normal request

```python
from pymcp.registry import tool_registry


@tool_registry.register(
    execution={
        "taskSupport": "optional",
        "runner": "async",
    }
)
async def build_index(repo: str) -> str:
    return f"Indexed {repo}"
```

## Injected Task Helpers

When the tool signature asks for them, the runtime can inject:

- `cancel_token`
- `task_context`
- `request_context`

`task_context` exposes helpers like:

- `await task_context.send_progress(...)`
- `await task_context.require_input(...)`
- `await task_context.set_working(...)`

`cancel_token` lets the tool stop cooperatively.

## Example: Progress, Cancellation, And Elicitation

```python
import asyncio

from pymcp.registry import tool_registry
from pymcp.runtime.context import RequestContext
from pymcp.session import request_elicitation
from pymcp.tasks import CancellationToken


@tool_registry.register(
    execution={
        "taskSupport": "optional",
        "runner": "async",
    }
)
async def review_repository(
    repo: str,
    cancel_token: CancellationToken | None = None,
    task_context=None,
    request_context: RequestContext | None = None,
) -> dict[str, object]:
    stages = ["clone", "index", "summarize"]

    for index, stage in enumerate(stages, start=1):
        if cancel_token is not None:
            cancel_token.check_cancelled()
        await asyncio.sleep(0)
        if task_context is not None:
            await task_context.send_progress(
                index,
                total=len(stages),
                message=f"Finished {stage} for {repo}",
            )

    if (
        task_context is not None
        and request_context is not None
        and request_context.session_id is not None
    ):
        await task_context.require_input("Choose the publish target before continuing.")
        _, response = await request_elicitation(
            request_context.app,
            request_context.session_id,
            {"message": "Which environment should receive the report?"},
            task_id=task_context.task_id,
        )
        await task_context.set_working("Continuing after user input.")

    return {
        "content": [{"type": "text", "text": f"Review complete for {repo}"}],
        "structuredContent": {"repo": repo, "status": "complete"},
    }
```

## Task RPC Surface

The built-in handlers expose:

- `tasks/list`
- `tasks/get`
- `tasks/cancel`
- `tasks/result`

Task-related flows also emit:

- `notifications/tasks/status`
- `notifications/progress`

If a tool returns a structured MCP result directly, `tasks/result` preserves that result shape instead of flattening it into plain text.

## Ownership And Access

Task visibility follows the caller context:

- without auth, tasks are scoped to the session
- with auth, tasks are bound to the authenticated principal

That means the same authenticated principal can access its tasks across sessions, while a different principal cannot.

## Notes

- If a client did not negotiate task support for `tools/call`, the runtime ignores task metadata and processes the tool call normally.
- Stdio and Streamable HTTP both support task side-channel traffic such as status and progress updates.
