"""Cooperative deadlines and cancellation for the Event inspection worker threads."""

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from bearagent.domain.errors import ErrorCode
from bearagent.ports.replay import replay_error


@dataclass
class ReadControl:
    deadline: float
    cancelled: threading.Event = field(default_factory=threading.Event)

    @property
    def stopped(self) -> bool:
        return self.cancelled.is_set() or time.monotonic() >= self.deadline

    def check(self) -> None:
        if self.stopped:
            raise replay_error(ErrorCode.QUERY_TIMEOUT)


async def run_bounded_read[T](work: Callable[[ReadControl], T], *, timeout_ms: int) -> T:
    """Signal cancellation and join the cooperative worker before returning to the caller."""
    control = ReadControl(time.monotonic() + timeout_ms / 1_000)
    task = asyncio.create_task(asyncio.to_thread(work, control))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        control.cancelled.set()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise
