"""Hard daily budget for replay runs (SPEC P6): exceeding stops, never warns.

The runner pre-authorizes every provider call against the remaining budget for
the current UTC day; actual spend is recorded after the call. The clock is
injected so tests control day boundaries.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


class DailyBudget:
    def __init__(self, cap_per_day_usd: Decimal, clock: Callable[[], datetime] = _utc_now) -> None:
        self.cap_per_day_usd = cap_per_day_usd
        self._clock = clock
        self._spent: dict[date, Decimal] = {}

    def _today(self) -> date:
        return self._clock().date()

    def spent_today(self) -> Decimal:
        return self._spent.get(self._today(), Decimal("0"))

    def remaining(self) -> Decimal:
        return max(Decimal("0"), self.cap_per_day_usd - self.spent_today())

    def can_spend(self, estimate: Decimal) -> bool:
        return estimate <= self.remaining()

    def record(self, actual: Decimal) -> None:
        today = self._today()
        self._spent[today] = self._spent.get(today, Decimal("0")) + actual
