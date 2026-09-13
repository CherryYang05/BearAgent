"""Explicit read-only Run reconstruction and bounded startup inspection."""

import time

from pydantic import ValidationError

from bearagent._bounded_read import run_bounded_read
from bearagent.domain.errors import ErrorCode
from bearagent.domain.ids import RunId
from bearagent.domain.replay import (
    DEFAULT_REPLAY_LIMITS,
    DEFAULT_SCAN_RUNS,
    MAX_SCAN_RUNS,
    ReplayLimits,
    RunCheckItem,
    RunCheckPage,
    RunReplay,
)
from bearagent.ports.replay import EventReplayError, EventReplaySource, replay_error
from bearagent.runtime.reducer import RunReducerError
from bearagent.runtime.replay import reconstruct_run


class RunReplayService:
    """Reports facts; has no ModelProvider, ToolExecutor, or writable store dependency."""

    def __init__(
        self, source: EventReplaySource, *, limits: ReplayLimits = DEFAULT_REPLAY_LIMITS
    ) -> None:
        self._source = source
        self._limits = limits

    async def replay(self, run_id: RunId) -> RunReplay:
        return await self._replay(run_id, self._deadline())

    async def check(
        self, *, after_run_id: RunId | None = None, limit: int = DEFAULT_SCAN_RUNS
    ) -> RunCheckPage:
        if type(limit) is not int or not 1 <= limit <= MAX_SCAN_RUNS:
            raise replay_error(ErrorCode.INVALID_INPUT)
        deadline = self._deadline()
        page = await self._source.list_event_run_ids(
            after_run_id=after_run_id, limit=limit, limits=self._remaining(deadline)
        )
        if page.after_run_id != after_run_id or page.limit != limit:
            raise replay_error(ErrorCode.INVALID_EVENT)
        items: list[RunCheckItem] = []
        for run_id in page.run_ids:
            self._remaining(deadline)
            try:
                # Keep only the content-free summary so a scan never retains all Run histories.
                summary = (await self._replay(run_id, deadline)).summary
                if summary.needs_attention:
                    items.append(RunCheckItem(run_id=run_id, summary=summary))
            except EventReplayError as error:
                items.append(RunCheckItem(run_id=run_id, error_code=error.info.code))
        self._remaining(deadline)
        return RunCheckPage(
            after_run_id=after_run_id,
            limit=limit,
            scanned_count=len(page.run_ids),
            items=tuple(items),
            next_after_run_id=page.next_after_run_id,
            has_more=page.has_more,
        )

    async def _replay(self, run_id: RunId, deadline: float) -> RunReplay:
        try:
            snapshot = await self._source.read_run_events(run_id, limits=self._remaining(deadline))
            if snapshot.run_id != run_id:
                raise replay_error(ErrorCode.INVALID_EVENT)
            limits = self._remaining(deadline)
            return await run_bounded_read(
                lambda control: reconstruct_run(snapshot, limits=limits, check=control.check),
                timeout_ms=limits.timeout_ms,
            )
        except (RunReducerError, ValidationError, KeyError, ValueError) as error:
            raise replay_error(ErrorCode.INVALID_EVENT) from error

    def _deadline(self) -> float:
        return time.monotonic() + self._limits.timeout_ms / 1_000

    def _remaining(self, deadline: float) -> ReplayLimits:
        remaining = int((deadline - time.monotonic()) * 1_000)
        if remaining < 1:
            raise replay_error(ErrorCode.QUERY_TIMEOUT)
        return self._limits.model_copy(update={"timeout_ms": remaining})
