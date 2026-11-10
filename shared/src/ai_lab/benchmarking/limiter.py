"""Request throttling and the daily request budget."""

import asyncio
import time
from collections.abc import Awaitable, Callable


class BudgetExhaustedError(Exception):
    """The request budget has no requests left."""


class RequestBudget:
    """Counts every request sent against a hard cap."""

    def __init__(self, cap: int, already_used: int = 0) -> None:
        self._cap = cap
        self._used = already_used

    @property
    def used(self) -> int:
        """Requests counted so far (including those used earlier today)."""
        return self._used

    @property
    def remaining(self) -> int:
        """Requests left before the cap."""
        return max(0, self._cap - self._used)

    def consume(self) -> None:
        """Count one request or raise if the cap is reached."""
        if self._used >= self._cap:
            raise BudgetExhaustedError(f"Request budget of {self._cap} exhausted")
        self._used += 1


class MinIntervalLimiter:
    """Ensures a minimum gap between consecutive request starts."""

    def __init__(
        self,
        per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._interval = 60.0 / per_minute
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    async def wait(self) -> None:
        """Sleep as needed, then mark a request start."""
        if self._last is not None:
            delay = self._last + self._interval - self._clock()
            if delay > 0:
                await self._sleep(delay)
        self._last = self._clock()


def before_request_hook(
    limiter: MinIntervalLimiter, budget: RequestBudget
) -> Callable[[], Awaitable[None]]:
    """Hook run before every attempt: throttle, then count against the budget."""

    async def hook() -> None:
        await limiter.wait()
        budget.consume()

    return hook
