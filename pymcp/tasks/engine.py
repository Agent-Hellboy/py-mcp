"""Task management for task-augmented MCP requests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType
from typing import Final, TypeAlias, cast
from uuid import uuid4

from fastapi import FastAPI

from ..observability.logging import get_logger
from ..protocol.json_types import JSONObject
from ..security.authn import Principal
from ..session.queueing import get_session_outbound_queue
from ..session.types import Session
from ..util.state_machine import AsyncStateMachine, Transition
from .progress import ProgressTracker


log = get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _principal_owner_key(principal: Principal | None) -> str | None:
    if principal is None:
        return None
    payload = {
        "subject": principal.subject,
        "displayName": principal.display_name,
        "scopes": sorted(principal.scopes),
        "roles": sorted(principal.roles),
        "claims": dict(principal.claims),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"principal:{hashlib.sha256(encoded).hexdigest()}"


def _task_owner_key(session_id: str, principal: Principal | None) -> str:
    principal_key = _principal_owner_key(principal)
    if principal_key is not None:
        return principal_key
    return f"session:{session_id}"


class TaskStatus(str, Enum):
    WORKING = "working"
    INPUT_REQUIRED = "input_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskEvent(str, Enum):
    RESUME = "resume"
    INPUT_NEEDED = "input_needed"
    COMPLETE = "complete"
    FAIL = "fail"
    CANCEL = "cancel"


TaskStatusValue: TypeAlias = TaskStatus

TERMINAL_TASK_STATUSES: Final[frozenset[TaskStatus]] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)

_TASK_TRANSITIONS: Mapping[
    TaskStatusValue,
    Mapping[TaskEvent, Transition[TaskStatusValue, TaskEvent]],
] = MappingProxyType(
    {
        TaskStatus.WORKING: MappingProxyType(
            {
                TaskEvent.INPUT_NEEDED: Transition(TaskStatus.INPUT_REQUIRED),
                TaskEvent.COMPLETE: Transition(TaskStatus.COMPLETED),
                TaskEvent.FAIL: Transition(TaskStatus.FAILED),
                TaskEvent.CANCEL: Transition(TaskStatus.CANCELLED),
            }
        ),
        TaskStatus.INPUT_REQUIRED: MappingProxyType(
            {
                TaskEvent.RESUME: Transition(TaskStatus.WORKING),
                TaskEvent.COMPLETE: Transition(TaskStatus.COMPLETED),
                TaskEvent.FAIL: Transition(TaskStatus.FAILED),
                TaskEvent.CANCEL: Transition(TaskStatus.CANCELLED),
            }
        ),
        TaskStatus.COMPLETED: MappingProxyType({}),
        TaskStatus.FAILED: MappingProxyType({}),
        TaskStatus.CANCELLED: MappingProxyType({}),
    }
)

_STATUS_TO_EVENT: Mapping[TaskStatusValue, TaskEvent] = MappingProxyType(
    {
        TaskStatus.WORKING: TaskEvent.RESUME,
        TaskStatus.INPUT_REQUIRED: TaskEvent.INPUT_NEEDED,
        TaskStatus.COMPLETED: TaskEvent.COMPLETE,
        TaskStatus.FAILED: TaskEvent.FAIL,
        TaskStatus.CANCELLED: TaskEvent.CANCEL,
    }
)


class TaskStateMachine:
    """Encapsulates allowed task transitions."""

    def __init__(self) -> None:
        self._machine: AsyncStateMachine[TaskStatusValue, TaskEvent] = AsyncStateMachine(
            initial=TaskStatus.WORKING,
            transitions=dict(_TASK_TRANSITIONS),
            name="task",
        )

    @property
    def state(self) -> TaskStatusValue:
        return self._machine.state

    async def transition(self, event: TaskEvent) -> TaskStatusValue:
        return await self._machine.trigger(event)


@dataclass
class TaskRecord:
    task_id: str
    session_id: str
    owner_key: str
    status: TaskStatusValue = TaskStatus.WORKING
    created_at: datetime = field(default_factory=_utc_now)
    last_updated_at: datetime = field(default_factory=_utc_now)
    ttl: int | None = None
    poll_interval: int | None = None
    status_message: str | None = None
    result: JSONObject | None = None
    error: JSONObject | None = None
    completion_event: asyncio.Event = field(default_factory=asyncio.Event)
    execution_handle: asyncio.Future[object] | None = None
    cancel_token_id: str | None = None
    progress_token: str | None = None
    state_machine: TaskStateMachine = field(default_factory=TaskStateMachine)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATUSES

    def is_expired(self, now: datetime) -> bool:
        if self.ttl is None:
            return False
        expires_at = self.created_at + timedelta(milliseconds=self.ttl)
        return now > expires_at

    def to_wire(self) -> JSONObject:
        payload: JSONObject = {
            "taskId": self.task_id,
            "status": self.status.value,
            "createdAt": _isoformat(self.created_at),
            "lastUpdatedAt": _isoformat(self.last_updated_at),
            "ttl": self.ttl,
        }
        if self.status_message:
            payload["statusMessage"] = self.status_message
        if self.poll_interval is not None:
            payload["pollInterval"] = self.poll_interval
        return payload


class TaskManager:
    """Manage tasks per session with TTL enforcement."""

    def __init__(
        self,
        default_ttl_ms: int = 60 * 60 * 1000,
        default_poll_interval: int = 5000,
        result_wait_timeout_ms: int = 5 * 60 * 1000,
    ):
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()
        self._default_ttl = default_ttl_ms
        self._default_poll_interval = default_poll_interval
        self.result_wait_timeout_ms = max(1, int(result_wait_timeout_ms))
        self._task_handles: dict[str, asyncio.Future[object]] = {}

    async def create_task(
        self,
        session_id: str,
        *,
        principal: Principal | None = None,
        ttl: int | None = None,
        poll_interval: int | None = None,
        progress_token: str | None = None,
    ) -> TaskRecord:
        async with self._lock:
            task_id = str(uuid4())
            if progress_token is None:
                progress_token = f"task:{task_id}"
            now = _utc_now()
            record = TaskRecord(
                task_id=task_id,
                session_id=session_id,
                owner_key=_task_owner_key(session_id, principal),
                created_at=now,
                last_updated_at=now,
                ttl=self._resolve_ttl(ttl),
                poll_interval=poll_interval if poll_interval is not None else self._default_poll_interval,
                status_message="Task accepted",
                progress_token=progress_token,
            )
            self._tasks[task_id] = record
            return record

    @staticmethod
    def _can_access(record: TaskRecord, session_id: str, principal: Principal | None) -> bool:
        return record.owner_key == _task_owner_key(session_id, principal)

    def _expire_task(self, task_id: str) -> None:
        record = self._tasks.pop(task_id, None)
        handle = self._task_handles.pop(task_id, None)
        if handle is not None and not handle.done():
            handle.cancel()
        if record is not None:
            record.execution_handle = None

    async def get_task_unchecked(self, task_id: str) -> TaskRecord | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return None
            if record.is_expired(_utc_now()):
                self._expire_task(task_id)
                return None
            return record

    async def get_progress_token(self, task_id: str) -> str | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            return record.progress_token if record else None

    async def set_cancel_token(self, task_id: str, token_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.cancel_token_id = token_id

    async def set_task_handle(self, task_id: str, handle: asyncio.Future[object]) -> None:
        async with self._lock:
            if task_id in self._tasks:
                self._task_handles[task_id] = handle
                self._tasks[task_id].execution_handle = handle

    def _status_to_event(self, status: TaskStatusValue) -> TaskEvent | None:
        return _STATUS_TO_EVENT.get(status)

    async def clear_task_handle(self, task_id: str) -> None:
        async with self._lock:
            self._task_handles.pop(task_id, None)
            record = self._tasks.get(task_id)
            if record:
                record.execution_handle = None

    async def cancel_task_handle(self, task_id: str) -> None:
        async with self._lock:
            handle = self._task_handles.get(task_id)
            if handle and not handle.done():
                handle.cancel()

    async def _apply_transition(
        self,
        record: TaskRecord,
        event: TaskEvent,
        *,
        status_message: str | None = None,
    ) -> TaskRecord:
        prev_status = record.status
        next_status = await record.state_machine.transition(event)
        if next_status == prev_status:
            return record
        record.status = next_status
        record.last_updated_at = _utc_now()
        record.status_message = status_message or record.status_message
        if record.is_terminal():
            record.completion_event.set()
            self._task_handles.pop(record.task_id, None)
            record.execution_handle = None
        return record

    async def get_task(
        self,
        task_id: str,
        session_id: str,
        *,
        principal: Principal | None = None,
    ) -> TaskRecord | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if not record or not self._can_access(record, session_id, principal):
                return None
            if record.is_expired(_utc_now()):
                self._expire_task(task_id)
                return None
            return record

    async def list_tasks(
        self,
        session_id: str,
        cursor: str | None,
        *,
        principal: Principal | None = None,
        page_size: int = 50,
    ) -> tuple[list[TaskRecord], str | None, str | None]:
        async with self._lock:
            now = _utc_now()
            expired = [task_id for task_id, record in self._tasks.items() if record.is_expired(now)]
            for task_id in expired:
                self._expire_task(task_id)
            tasks = [
                record
                for record in self._tasks.values()
                if self._can_access(record, session_id, principal)
            ]
            tasks.sort(key=lambda record: record.created_at, reverse=True)
            start = 0
            if cursor:
                try:
                    start = int(cursor)
                except (TypeError, ValueError):
                    return [], None, "Invalid cursor"
            slice_tasks = tasks[start : start + page_size]
            next_cursor = str(start + page_size) if start + page_size < len(tasks) else None
            return slice_tasks, next_cursor, None

    async def complete_task(
        self,
        task_id: str,
        *,
        status: TaskStatusValue,
        result: JSONObject | None = None,
        error: JSONObject | None = None,
        status_message: str | None = None,
    ) -> TaskRecord | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if not record or record.is_terminal():
                return record
            event = self._status_to_event(status)
            if event is None:
                return record
            record.result = result
            record.error = error
            record.status_message = status_message
            return await self._apply_transition(record, event, status_message=status_message)

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatusValue,
        *,
        status_message: str | None = None,
    ) -> TaskRecord | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if not record or record.is_terminal() or record.status == status:
                return record
            event = self._status_to_event(status)
            if event is None:
                return record
            return await self._apply_transition(record, event, status_message=status_message)

    async def mark_task_cancelled(
        self,
        task_id: str,
        session_id: str,
        *,
        principal: Principal | None = None,
    ) -> TaskRecord | None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if not record or not self._can_access(record, session_id, principal):
                return None
            if record.is_terminal():
                return record
            record.status_message = "The task was cancelled by request."
            return await self._apply_transition(record, TaskEvent.CANCEL, status_message=record.status_message)

    def _resolve_ttl(self, requested_ttl: int | None) -> int | None:
        if requested_ttl is None:
            return self._default_ttl
        return max(0, int(requested_ttl))


def get_task_manager(app: FastAPI) -> TaskManager:
    if not hasattr(app.state, "task_manager"):
        app.state.task_manager = TaskManager()
    return cast(TaskManager, app.state.task_manager)


def get_task_executor(app: FastAPI, max_workers: int = 8) -> ThreadPoolExecutor:
    if not hasattr(app.state, "task_executor"):
        app.state.task_executor = ThreadPoolExecutor(max_workers=max_workers)
    return cast(ThreadPoolExecutor, app.state.task_executor)


class TaskContext:
    """Surface task-related helpers to tool implementations."""

    def __init__(
        self,
        task_id: str,
        session: Session,
        task_manager: TaskManager,
        queue: asyncio.Queue[str],
        *,
        progress_token: str | None = None,
        app: FastAPI | None = None,
        session_id: str | None = None,
    ):
        self.task_id = task_id
        self.app = app
        self.session_id = session_id or session.session_id
        self._session = session
        self._task_manager = task_manager
        self._queue = queue
        self._progress_tracker = ProgressTracker(session)
        self._progress_started = False
        self._progress_token = progress_token

    async def require_input(self, message: str | None = None) -> None:
        record = await self._task_manager.update_task_status(
            self.task_id,
            TaskStatus.INPUT_REQUIRED,
            status_message=message,
        )
        if record:
            await self._enqueue_status(record)

    async def set_working(self, message: str | None = None) -> None:
        record = await self._task_manager.update_task_status(
            self.task_id,
            TaskStatus.WORKING,
            status_message=message,
        )
        if record:
            await self._enqueue_status(record)

    async def send_progress(
        self,
        current: int,
        total: int | None = None,
        message: str | None = None,
    ) -> None:
        token = self._progress_token
        if not token:
            return
        record = await self._task_manager.get_task_unchecked(self.task_id)
        if not record or record.is_terminal():
            return
        self._progress_started = True
        await self._progress_tracker.set_progress(
            token,
            current=current,
            total=total,
            message=message,
            task_id=self.task_id,
        )

    async def finish_progress(self, message: str | None = None) -> None:
        if self._progress_started and self._progress_token:
            try:
                await self._progress_tracker.complete(self._progress_token, message=message)
            finally:
                self._progress_started = False

    async def _enqueue_status(self, record: TaskRecord) -> None:
        notification: JSONObject = {
            "jsonrpc": "2.0",
            "method": "notifications/tasks/status",
            "params": record.to_wire(),
        }
        await get_session_outbound_queue(self._session).put(json.dumps(notification))


__all__ = [
    "TERMINAL_TASK_STATUSES",
    "TaskContext",
    "TaskEvent",
    "TaskManager",
    "TaskRecord",
    "TaskStateMachine",
    "TaskStatus",
    "TaskStatusValue",
    "get_task_executor",
    "get_task_manager",
]
