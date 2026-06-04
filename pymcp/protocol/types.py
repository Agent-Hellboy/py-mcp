"""Type definitions for MCP JSON-RPC protocol messages."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator

from .json_types import JSONArray, JSONObject, JSONValue, RPCId
from .tool_execution import ToolExecutionConfig


class JSONRPCError(BaseModel):
    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: JSONValue | None = Field(default=None, description="Optional additional error information")


class JSONRPCRequest(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(..., description="Method name")
    params: JSONObject | JSONArray | None = Field(default=None, description="Parameters")
    id: RPCId = Field(default=None, description="Request ID")

    @model_validator(mode="after")
    def validate_jsonrpc_version(self) -> "JSONRPCRequest":
        if self.jsonrpc != "2.0":
            raise ValueError("jsonrpc MUST be exactly '2.0'")
        return self


class JSONRPCNotification(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(..., description="Method name")
    params: JSONObject | JSONArray | None = Field(default=None, description="Parameters")

    @model_validator(mode="after")
    def validate_jsonrpc_version(self) -> "JSONRPCNotification":
        if self.jsonrpc != "2.0":
            raise ValueError("jsonrpc MUST be exactly '2.0'")
        return self


class JSONRPCResponse(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    id: RPCId = Field(..., description="Request ID")
    result: JSONObject | None = Field(default=None, description="Success result")
    error: JSONRPCError | None = Field(default=None, description="Error result")

    @model_validator(mode="after")
    def validate_jsonrpc_version(self) -> "JSONRPCResponse":
        if self.jsonrpc != "2.0":
            raise ValueError("jsonrpc MUST be exactly '2.0'")
        return self

    @model_validator(mode="after")
    def validate_result_or_error(self) -> "JSONRPCResponse":
        has_result = self.result is not None
        has_error = self.error is not None
        if not has_result and not has_error:
            raise ValueError("Response must have either 'result' or 'error'")
        if has_result and has_error:
            raise ValueError("Response cannot have both 'result' and 'error'")
        return self


class Annotations(BaseModel):
    """Content annotations placeholder."""


class TextContent(BaseModel):
    type: str = Field(default="text", description="Content type")
    text: str = Field(..., description="Text content")
    annotations: Annotations | None = Field(default=None, description="Optional annotations")


class ImageContent(BaseModel):
    type: str = Field(default="image", description="Content type")
    data: str = Field(..., description="Base64-encoded image data")
    mimeType: str = Field(..., description="MIME type")


class AudioContent(BaseModel):
    type: str = Field(default="audio", description="Content type")
    data: str = Field(..., description="Base64-encoded audio data")
    mimeType: str = Field(..., description="MIME type")


class ResourceContents(BaseModel):
    uri: str = Field(..., description="Resource URI")
    mimeType: str = Field(..., description="MIME type")


class TextResourceContents(ResourceContents):
    text: str = Field(..., description="Text content")


class BlobResourceContents(ResourceContents):
    blob: str = Field(..., description="Base64-encoded blob data")


class EmbeddedResource(BaseModel):
    type: str = Field(default="resource", description="Content type")
    resource: ResourceContents = Field(..., description="Embedded resource")


ContentBlock: TypeAlias = TextContent | ImageContent | AudioContent | EmbeddedResource


class CallToolResult(BaseModel):
    content: list[ContentBlock] = Field(..., description="Content blocks")
    isError: bool = Field(default=False, description="Whether this is an error result")
    annotations: Annotations | None = Field(default=None, description="Optional annotations")


class Task(BaseModel):
    taskId: str = Field(..., description="Task identifier")
    status: Literal["working", "input_required", "completed", "failed", "cancelled"] = Field(
        ...,
        description="Task status",
    )
    statusMessage: str | None = Field(default=None, description="Human-readable status")
    createdAt: str = Field(..., description="Creation timestamp")
    lastUpdatedAt: str = Field(..., description="Last update timestamp")
    ttl: int | None = Field(default=None, description="TTL in milliseconds")
    pollInterval: int | None = Field(default=None, description="Suggested poll interval in milliseconds")


class CreateTaskResult(BaseModel):
    task: Task = Field(..., description="Created task descriptor")


class TasksListResult(BaseModel):
    tasks: list[Task] = Field(..., description="Tasks visible to the caller")
    nextCursor: str | None = Field(default=None, description="Opaque pagination cursor")


class Tool(BaseModel):
    name: str = Field(..., description="Tool name")
    description: str | None = Field(default=None, description="Tool description")
    inputSchema: JSONObject = Field(..., description="JSON Schema for input parameters")
    execution: ToolExecutionConfig | None = Field(default=None, description="Execution metadata")
    annotations: Annotations | None = Field(default=None, description="Optional annotations")


class CallToolRequestParams(BaseModel):
    name: str = Field(..., description="Tool name")
    arguments: JSONObject | None = Field(default=None, description="Tool arguments")


class ListToolsResult(BaseModel):
    tools: list[Tool] = Field(..., description="List of tools")


class PromptArgument(BaseModel):
    name: str = Field(..., description="Argument name")
    description: str | None = Field(default=None, description="Argument description")
    required: bool = Field(default=False, description="Whether the argument is required")


class Prompt(BaseModel):
    name: str = Field(..., description="Prompt name")
    description: str | None = Field(default=None, description="Prompt description")
    arguments: list[PromptArgument] | None = Field(default=None, description="Prompt arguments")


class GetPromptRequestParams(BaseModel):
    name: str = Field(..., description="Prompt name")
    arguments: JSONObject | None = Field(default=None, description="Prompt arguments")


class ListPromptsResult(BaseModel):
    prompts: list[Prompt] = Field(..., description="List of prompts")


class PromptMessage(BaseModel):
    role: str = Field(..., description="Message role")
    content: ContentBlock = Field(..., description="Message content")


class GetPromptResult(BaseModel):
    description: str | None = Field(default=None, description="Prompt description")
    messages: list[PromptMessage] = Field(..., description="Prompt messages")


class Resource(BaseModel):
    uri: str = Field(..., description="Resource URI")
    name: str = Field(..., description="Resource name")
    description: str | None = Field(default=None, description="Resource description")
    mimeType: str | None = Field(default=None, description="MIME type")


class ListResourcesResult(BaseModel):
    resources: list[Resource] = Field(..., description="List of resources")


class Root(BaseModel):
    uri: str = Field(..., description="Root URI")
    name: str | None = Field(default=None, description="Optional human-readable name")


class ListRootsResult(BaseModel):
    roots: list[Root] = Field(..., description="List of roots")


class ElicitationCreateParams(BaseModel):
    mode: Literal["form", "url"] | None = Field(default="form", description="Elicitation mode")
    message: str = Field(..., description="Prompt shown to the user")
    requestedSchema: JSONObject | None = Field(default=None, description="JSON Schema for form mode")
    url: str | None = Field(default=None, description="URL for url mode elicitation")
    elicitationId: str | None = Field(default=None, description="Unique URL elicitation identifier")


class ElicitationResult(BaseModel):
    action: Literal["accept", "decline", "cancel"] = Field(..., description="User action")
    content: JSONObject | None = Field(default=None, description="User-provided content")


class ElicitationCompleteNotificationParams(BaseModel):
    elicitationId: str = Field(..., description="Elicitation identifier")


# ---------------------------------------------------------------------------
# Sampling types (server -> client)
# ---------------------------------------------------------------------------


class ModelHint(BaseModel):
    name: str | None = Field(default=None, description="Model name hint (substring match)")


class ModelPreferences(BaseModel):
    hints: list[ModelHint] | None = Field(default=None, description="Ordered model hints")
    costPriority: float | None = Field(default=None, description="Cost priority (0-1)")
    speedPriority: float | None = Field(default=None, description="Speed priority (0-1)")
    intelligencePriority: float | None = Field(default=None, description="Intelligence priority (0-1)")


class ToolUseContent(BaseModel):
    type: str = Field(default="tool_use", description="Content type")
    id: str = Field(..., description="Tool use identifier")
    name: str = Field(..., description="Tool name")
    input: JSONObject = Field(..., description="Tool arguments")


class ToolResultContent(BaseModel):
    type: str = Field(default="tool_result", description="Content type")
    toolUseId: str = Field(..., description="Matching tool use identifier")
    content: list[TextContent | ImageContent | AudioContent] | None = Field(
        default=None, description="Result content blocks"
    )
    isError: bool = Field(default=False, description="Whether the tool returned an error")


class SamplingToolDefinition(BaseModel):
    name: str = Field(..., description="Tool name")
    description: str | None = Field(default=None, description="Tool description")
    inputSchema: JSONObject = Field(..., description="JSON Schema for tool input")


class ToolChoice(BaseModel):
    mode: Literal["none", "auto", "required"] = Field(
        default="auto", description="Tool use mode"
    )


SamplingContentBlock: TypeAlias = (
    TextContent | ImageContent | AudioContent | ToolUseContent | ToolResultContent
)


class CreateMessageRequestParams(BaseModel):
    messages: list[JSONObject] = Field(..., description="Conversation messages")
    modelPreferences: ModelPreferences | None = Field(default=None, description="Model selection preferences")
    systemPrompt: str | None = Field(default=None, description="System prompt")
    includeContext: str | None = Field(default=None, description="Context inclusion (soft-deprecated)")
    maxTokens: int = Field(..., description="Maximum tokens to generate")
    tools: list[SamplingToolDefinition] | None = Field(default=None, description="Tools available to LLM")
    toolChoice: ToolChoice | None = Field(default=None, description="Tool use control")


class CreateMessageResult(BaseModel):
    role: str = Field(..., description="Message role (assistant)")
    content: JSONValue = Field(..., description="Response content")
    model: str = Field(..., description="Model used")
    stopReason: str | None = Field(default=None, description="Stop reason (endTurn, toolUse, etc.)")


# ---------------------------------------------------------------------------
# Logging types (server -> client notification)
# ---------------------------------------------------------------------------


class LoggingMessageNotificationParams(BaseModel):
    level: str = Field(..., description="Log level (debug, info, warning, error, critical, alert, emergency)")
    logger: str | None = Field(default=None, description="Logger name")
    data: JSONValue | None = Field(default=None, description="Arbitrary log data")


# ---------------------------------------------------------------------------
# Completions types (client -> server)
# ---------------------------------------------------------------------------


class CompletionRef(BaseModel):
    type: str = Field(..., description="Reference type (ref/prompt or ref/resource)")
    name: str | None = Field(default=None, description="Prompt name (for ref/prompt)")
    uri: str | None = Field(default=None, description="Resource URI (for ref/resource)")


class CompletionArgument(BaseModel):
    name: str = Field(..., description="Argument name")
    value: str = Field(..., description="Partial argument value to complete")


class CompleteRequestParams(BaseModel):
    ref: CompletionRef = Field(..., description="Reference to complete against")
    argument: CompletionArgument = Field(..., description="Argument to complete")


class Completion(BaseModel):
    values: list[str] = Field(..., description="Completion suggestions")
    hasMore: bool = Field(default=False, description="Whether more completions exist")
    total: int | None = Field(default=None, description="Total number of completions")


class CompleteResult(BaseModel):
    completion: Completion = Field(..., description="Completion result")


# ---------------------------------------------------------------------------
# Resource read
# ---------------------------------------------------------------------------


class ReadResourceRequestParams(BaseModel):
    uri: str = Field(..., description="Resource URI")


class ReadResourceResult(BaseModel):
    contents: list[ResourceContents] = Field(..., description="Resource contents")


class ProgressNotificationParams(BaseModel):
    progressToken: str | None = Field(default=None, description="Progress token")
    progress: float | None = Field(default=None, description="Progress value")
    total: int | None = Field(default=None, description="Optional total progress target")
    message: str | None = Field(default=None, description="Optional progress message")


class ProgressNotification(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(default="notifications/progress", description="Notification method")
    params: ProgressNotificationParams = Field(..., description="Progress parameters")


class ServerInfo(BaseModel):
    name: str = Field(..., description="Server name")
    version: str = Field(..., description="Server version")


class InitializeParams(BaseModel):
    protocolVersion: str | None = Field(default="2025-03-26", description="Requested protocol version")
    capabilities: JSONObject | None = Field(default=None, description="Client capabilities")
    clientInfo: JSONObject | None = Field(default=None, description="Client information")


class InitializeResult(BaseModel):
    protocolVersion: str = Field(..., description="Accepted protocol version")
    capabilities: JSONObject = Field(..., description="Negotiated server capabilities")
    serverInfo: ServerInfo = Field(..., description="Server information")


class CancelledNotificationParams(BaseModel):
    requestId: RPCId = Field(..., description="Request identifier to cancel")
    reason: str | None = Field(default=None, description="Optional cancellation reason")


class CancelledNotification(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(default="notifications/cancelled", description="Notification method")
    params: CancelledNotificationParams = Field(..., description="Cancellation parameters")


class ToolsListChangedNotification(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(default="notifications/tools/list_changed", description="Notification method")


class PromptsListChangedNotification(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(default="notifications/prompts/list_changed", description="Notification method")


class ResourcesListChangedNotification(BaseModel):
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(default="notifications/resources/list_changed", description="Notification method")


__all__ = [
    "Annotations",
    "AudioContent",
    "BlobResourceContents",
    "CallToolRequestParams",
    "CallToolResult",
    "CancelledNotification",
    "CancelledNotificationParams",
    "CompleteRequestParams",
    "CompleteResult",
    "Completion",
    "CompletionArgument",
    "CompletionRef",
    "ContentBlock",
    "CreateMessageRequestParams",
    "CreateMessageResult",
    "CreateTaskResult",
    "ElicitationCompleteNotificationParams",
    "ElicitationCreateParams",
    "ElicitationResult",
    "EmbeddedResource",
    "GetPromptRequestParams",
    "GetPromptResult",
    "ImageContent",
    "InitializeParams",
    "InitializeResult",
    "JSONRPCError",
    "JSONRPCNotification",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "ListPromptsResult",
    "ListResourcesResult",
    "ListRootsResult",
    "ListToolsResult",
    "LoggingMessageNotificationParams",
    "ModelHint",
    "ModelPreferences",
    "ProgressNotification",
    "ProgressNotificationParams",
    "Prompt",
    "PromptArgument",
    "PromptMessage",
    "PromptsListChangedNotification",
    "ReadResourceRequestParams",
    "ReadResourceResult",
    "Resource",
    "ResourceContents",
    "ResourcesListChangedNotification",
    "Root",
    "SamplingContentBlock",
    "SamplingToolDefinition",
    "ServerInfo",
    "Task",
    "TasksListResult",
    "TextContent",
    "TextResourceContents",
    "Tool",
    "ToolChoice",
    "ToolResultContent",
    "ToolUseContent",
    "ToolsListChangedNotification",
]
