import json

import pytest

from pymcp import create_app
from pymcp.session import get_session_manager
from pymcp.tasks.progress import ProgressTracker, build_progress_notification


pytestmark = pytest.mark.anyio


async def test_progress_tracker_emits_notifications():
    app = create_app(middleware_config=None)
    session = get_session_manager(app).create_session()
    tracker = ProgressTracker(session)

    await tracker.start("pt-1", total=3, message="start")
    await tracker.update("pt-1", increment=1, message="middle")
    await tracker.complete("pt-1", message="done")

    messages = [json.loads(await session.queue.get()) for _ in range(3)]
    assert [message["method"] for message in messages] == [
        "notifications/progress",
        "notifications/progress",
        "notifications/progress",
    ]
    assert messages[0]["params"]["progress"] == 0
    assert messages[1]["params"]["progress"] == 1
    assert messages[2]["params"]["progress"] == 3
    assert messages[2]["params"]["message"] == "done"


def test_build_progress_notification_includes_task_meta():
    payload = build_progress_notification(
        "pt-2",
        2,
        total=5,
        message="step 2",
        task_id="task-1",
    )

    assert payload["method"] == "notifications/progress"
    assert payload["params"]["progressToken"] == "pt-2"
    assert payload["_meta"]["io.modelcontextprotocol/related-task"]["taskId"] == "task-1"
