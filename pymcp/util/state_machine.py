"""Async state machine helper used by lifecycle-driven runtime components."""

from __future__ import annotations

import asyncio
import contextvars
import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, TypeVar, cast


StateT = TypeVar("StateT", bound=str)
EventT = TypeVar("EventT", bound=str)

Guard = Callable[[StateT, EventT], bool | Awaitable[bool]]
TransitionAction = Callable[[StateT, StateT, EventT], None | Awaitable[None]]
TransitionObserver = Callable[[StateT, StateT, EventT, str], None | Awaitable[None]]
StateAction = Callable[[StateT, EventT], None | Awaitable[None]]

_IN_HOOK: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "pymcp_in_state_machine_hook",
    default=False,
)


@dataclass(frozen=True)
class Transition(Generic[StateT, EventT]):
    target: StateT
    guard: Guard[StateT, EventT] | None = None
    on_transition: TransitionAction[StateT, EventT] | None = None


class AsyncStateMachine(Generic[StateT, EventT]):
    """Async-safe state machine with serialized hook execution."""

    def __init__(
        self,
        *,
        initial: StateT,
        transitions: dict[StateT, dict[EventT, Transition[StateT, EventT]]],
        name: str = "state_machine",
        on_any_transition: TransitionObserver[StateT, EventT] | None = None,
        on_enter: dict[StateT, StateAction[StateT, EventT]] | None = None,
        on_exit: dict[StateT, StateAction[StateT, EventT]] | None = None,
    ) -> None:
        self._state = initial
        self._transitions = transitions
        self._name = name
        self._lock = asyncio.Lock()
        self._on_any_transition = on_any_transition
        self._on_enter = on_enter or {}
        self._on_exit = on_exit or {}
        self._hook_tail: asyncio.Future[None] | None = None

    @property
    def state(self) -> StateT:
        return self._state

    def can(self, event: EventT) -> bool:
        return event in self._transitions.get(self._state, {})

    def trigger_later(self, event: EventT) -> asyncio.Task[StateT]:
        token = _IN_HOOK.set(False)
        try:
            return asyncio.get_running_loop().create_task(self.trigger(event))
        finally:
            _IN_HOOK.reset(token)

    async def trigger(self, event: EventT) -> StateT:
        if _IN_HOOK.get():
            raise RuntimeError(
                f"{self._name}: trigger({event!r}) called from within a hook; use trigger_later() instead"
            )

        next_state, after_hooks, previous_tail, current_tail = await self._commit(event)
        if after_hooks and previous_tail and current_tail:
            await self._run_after_hooks(after_hooks, previous_tail, current_tail)
        return next_state

    async def _commit(
        self,
        event: EventT,
    ) -> tuple[
        StateT,
        list[Callable[[], None | Awaitable[None]]],
        asyncio.Future[None] | None,
        asyncio.Future[None] | None,
    ]:
        async with self._lock:
            previous_state = self._state
            transition = self._transitions.get(previous_state, {}).get(event)
            if transition is None:
                return previous_state, [], None, None

            if transition.guard is not None:
                allowed = transition.guard(previous_state, event)
                if inspect.isawaitable(allowed):
                    allowed = await cast(Awaitable[bool], allowed)
                if not allowed:
                    return previous_state, [], None, None

            self._state = transition.target
            current_state = self._state

            if transition.on_transition is not None:
                await self._invoke_hook(
                    lambda: transition.on_transition(previous_state, current_state, event)
                )

            after_hooks: list[Callable[[], None | Awaitable[None]]] = []
            if previous_state != current_state:
                exit_hook = self._on_exit.get(previous_state)
                if exit_hook is not None:
                    after_hooks.append(lambda: exit_hook(previous_state, event))
                enter_hook = self._on_enter.get(current_state)
                if enter_hook is not None:
                    after_hooks.append(lambda: enter_hook(current_state, event))

            if self._on_any_transition is not None:
                after_hooks.append(
                    lambda: self._on_any_transition(previous_state, current_state, event, self._name)
                )

            if not after_hooks:
                return current_state, after_hooks, None, None

            loop = asyncio.get_running_loop()
            if self._hook_tail is None:
                self._hook_tail = loop.create_future()
                self._hook_tail.set_result(None)

            previous_tail = self._hook_tail
            current_tail: asyncio.Future[None] = loop.create_future()
            self._hook_tail = current_tail
            return current_state, after_hooks, previous_tail, current_tail

    async def _run_after_hooks(
        self,
        after_hooks: list[Callable[[], None | Awaitable[None]]],
        previous_tail: asyncio.Future[None],
        current_tail: asyncio.Future[None],
    ) -> None:
        try:
            try:
                await previous_tail
            except Exception:
                pass

            for hook in after_hooks:
                await self._invoke_hook(hook)
        except asyncio.CancelledError:
            if not current_tail.done():
                current_tail.set_result(None)
            raise
        except Exception as exc:
            if not current_tail.done():
                current_tail.set_exception(exc)
            raise
        else:
            if not current_tail.done():
                current_tail.set_result(None)

    async def _invoke_hook(self, hook: Callable[[], None | Awaitable[None]]) -> None:
        token = _IN_HOOK.set(True)
        try:
            result = hook()
            if inspect.isawaitable(result):
                await cast(Awaitable[None], result)
        finally:
            _IN_HOOK.reset(token)
