"""Progress tracking helpers for long-running PyMCP operations."""

from __future__ import annotations

import json
from typing import Any

from typing_extensions import TypedDict

from ..session.queueing import get_session_outbound_queue
from ..session.types import Session


JSONObject = dict[str, Any]


class ProgressInfo(TypedDict, total=False):
    total: int | None
    current: int
    message: str | None
    task_id: str | None


class ProgressTracker:
    """Tracks progress tokens and emits MCP progress notifications."""

    def __init__(self, session: Session):
        self._session = session
        self.session_id = session.session_id
        self.active_progress: dict[str, ProgressInfo] = {}

    async def start(
        self,
        progress_token: str | None = None,
        total: int | None = None,
        message: str | None = None,
        task_id: str | None = None,
    ) -> str | None:
        """Start a progress stream and emit the initial notification."""

        if progress_token is None:
            return None

        self.active_progress[progress_token] = {
            "total": total,
            "current": 0,
            "message": message,
            "task_id": task_id,
        }
        await self._send_notification(progress_token, 0, total=total, message=message, task_id=task_id)
        return progress_token

    async def update(self, progress_token: str, increment: int = 1, message: str | None = None) -> None:
        """Increment progress and emit a notification."""

        if not progress_token or progress_token not in self.active_progress:
            return

        progress_info = self.active_progress[progress_token]
        progress_info["current"] += increment
        if message is not None:
            progress_info["message"] = message

        await self._send_notification(
            progress_token,
            progress_info["current"],
            total=progress_info.get("total"),
            message=progress_info.get("message"),
            task_id=progress_info.get("task_id"),
        )

    async def complete(self, progress_token: str, message: str | None = None) -> None:
        """Mark a progress stream complete and remove it from active tracking."""

        if not progress_token or progress_token not in self.active_progress:
            return

        progress_info = self.active_progress.pop(progress_token, None)
        if progress_info is None:
            return
        final_current = progress_info["total"] if progress_info.get("total") is not None else progress_info["current"]
        final_message = message if message is not None else progress_info.get("message")
        await self._send_notification(
            progress_token,
            final_current,
            total=progress_info.get("total"),
            message=final_message,
            task_id=progress_info.get("task_id"),
        )

    async def set_progress(
        self,
        progress_token: str,
        *,
        current: int,
        total: int | None = None,
        message: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Set absolute progress and emit a notification."""

        if not progress_token:
            return

        progress_info = self.active_progress.get(progress_token)
        if progress_info is None:
            progress_info = {
                "total": total,
                "current": current,
                "message": message,
                "task_id": task_id,
            }
            self.active_progress[progress_token] = progress_info
        else:
            progress_info["current"] = current
            if total is not None:
                progress_info["total"] = total
            if message is not None:
                progress_info["message"] = message
            if task_id is not None:
                progress_info["task_id"] = task_id

        await self._send_notification(
            progress_token,
            current,
            total=progress_info.get("total"),
            message=progress_info.get("message"),
            task_id=progress_info.get("task_id"),
        )

    async def _send_notification(
        self,
        progress_token: str,
        current: int,
        *,
        total: int | None = None,
        message: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Queue a progress notification to the current session."""

        await get_session_outbound_queue(self._session).put(
            json.dumps(
                build_progress_notification(
                    progress_token,
                    current,
                    total=total,
                    message=message,
                    task_id=task_id,
                )
            )
        )


def build_progress_notification(
    progress_token: str,
    current: int,
    total: int | None = None,
    message: str | None = None,
    task_id: str | None = None,
) -> JSONObject:
    """Build a JSON-RPC `notifications/progress` payload."""

    params: JSONObject = {
        "progressToken": progress_token,
        "progress": current,
    }
    if total is not None:
        params["total"] = total
    if message is not None:
        params["message"] = message

    payload: JSONObject = {
        "jsonrpc": "2.0",
        "method": "notifications/progress",
        "params": params,
    }
    if task_id:
        payload["_meta"] = {"io.modelcontextprotocol/related-task": {"taskId": task_id}}
    return payload
