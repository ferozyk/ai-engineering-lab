"""Unit tests for the rate limiter and request budget (fake clock, no sleeping)."""

import pytest

from ai_lab.benchmarking.limiter import (
    BudgetExhaustedError,
    MinIntervalLimiter,
    RequestBudget,
    before_request_hook,
)

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


class _FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_interval_is_enforced() -> None:
    fake = _FakeTime()
    limiter = MinIntervalLimiter(15, clock=fake.clock, sleep=fake.sleep)
    await limiter.wait()
    assert fake.sleeps == []
    await limiter.wait()
    assert fake.sleeps == [pytest.approx(4.0)]
    fake.now += 10.0
    await limiter.wait()
    assert len(fake.sleeps) == 1


def test_budget_consume_and_raise() -> None:
    budget = RequestBudget(2, already_used=1)
    assert (budget.used, budget.remaining) == (1, 1)
    budget.consume()
    assert budget.remaining == 0
    with pytest.raises(BudgetExhaustedError):
        budget.consume()
    assert budget.used == 2


async def test_hook_counts_every_attempt() -> None:
    fake = _FakeTime()
    budget = RequestBudget(10)
    hook = before_request_hook(MinIntervalLimiter(60, clock=fake.clock, sleep=fake.sleep), budget)
    for _ in range(3):
        await hook()
    assert budget.used == 3
    assert len(fake.sleeps) == 2
