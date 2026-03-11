import asyncio

import pytest

from pymcp.util.state_machine import AsyncStateMachine, Transition


pytestmark = pytest.mark.anyio("asyncio")


async def test_on_any_transition_hooks_are_serialized_in_commit_order():
    calls = []
    gate = asyncio.Event()

    async def observer(previous: str, current: str, event: str, name: str) -> None:
        calls.append((event, "start", previous, current, name))
        if event == "e1":
            await gate.wait()
        calls.append((event, "end", previous, current, name))

    state_machine = AsyncStateMachine(
        initial="A",
        name="sm",
        on_any_transition=observer,
        transitions={
            "A": {"e1": Transition("B")},
            "B": {"e2": Transition("C")},
            "C": {},
        },
    )

    first = asyncio.create_task(state_machine.trigger("e1"))
    await asyncio.sleep(0)
    second = asyncio.create_task(state_machine.trigger("e2"))
    await asyncio.sleep(0)

    assert calls == [("e1", "start", "A", "B", "sm")]

    gate.set()
    assert await first == "B"
    assert await second == "C"
    assert calls == [
        ("e1", "start", "A", "B", "sm"),
        ("e1", "end", "A", "B", "sm"),
        ("e2", "start", "B", "C", "sm"),
        ("e2", "end", "B", "C", "sm"),
    ]


async def test_entry_exit_hooks_run_before_observer():
    calls = []

    def on_exit(state: str, event: str) -> None:
        calls.append(("exit", state, event))

    def on_enter(state: str, event: str) -> None:
        calls.append(("enter", state, event))

    def observer(previous: str, current: str, event: str, name: str) -> None:
        calls.append(("any", previous, current, event, name))

    state_machine = AsyncStateMachine(
        initial="A",
        name="sm",
        on_any_transition=observer,
        on_exit={"A": on_exit, "B": on_exit},
        on_enter={"B": on_enter},
        transitions={
            "A": {"go": Transition("B")},
            "B": {"noop": Transition("B")},
        },
    )

    await state_machine.trigger("go")
    assert calls == [
        ("exit", "A", "go"),
        ("enter", "B", "go"),
        ("any", "A", "B", "go", "sm"),
    ]

    calls.clear()
    await state_machine.trigger("noop")
    assert calls == [("any", "B", "B", "noop", "sm")]


async def test_hooks_cannot_call_trigger_directly():
    state_machine: AsyncStateMachine[str, str]

    async def observer(_previous: str, _current: str, _event: str, _name: str) -> None:
        await state_machine.trigger("anything")

    state_machine = AsyncStateMachine(
        initial="A",
        name="sm",
        on_any_transition=observer,
        transitions={"A": {"go": Transition("A")}},
    )

    with pytest.raises(RuntimeError, match=r"use trigger_later\(\) instead"):
        await state_machine.trigger("go")


async def test_trigger_later_schedules_followup_event_from_hook():
    scheduled = []

    def observer(_previous: str, _current: str, event: str, _name: str) -> None:
        if event == "e1":
            scheduled.append(state_machine.trigger_later("e2"))

    state_machine = AsyncStateMachine(
        initial="A",
        name="sm",
        on_any_transition=observer,
        transitions={
            "A": {"e1": Transition("B")},
            "B": {"e2": Transition("C")},
            "C": {},
        },
    )

    assert await state_machine.trigger("e1") == "B"
    assert len(scheduled) == 1
    assert await scheduled[0] == "C"
    assert state_machine.state == "C"
