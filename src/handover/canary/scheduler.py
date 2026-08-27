"""Canary run planner (SPEC §6.2): hourly pulse n=30, daily n=600, weekly n=5000.

Pure planning — no model calls here. The pulse samples each model as a whole
(its only job is crash detection); daily and weekly runs are broken down per
cluster, with the per-model total allocated across clusters.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

Cadence = Literal["pulse", "daily", "weekly"]

CADENCE_N: dict[Cadence, int] = {"pulse": 30, "daily": 600, "weekly": 5000}
DAILY_HOUR_UTC = 6
WEEKLY_WEEKDAY = 0  # Monday


class CanaryRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    cluster_id: str | None  # None = whole-model mixed sample (pulse)
    cadence: Cadence
    n: int
    scheduled_at: datetime


class WindowStat(BaseModel):
    """One completed canary window for a model x cluster pair."""

    model_config = ConfigDict(frozen=True)

    ts: datetime
    n: int
    successes: int

    @property
    def rate(self) -> float:
        return self.successes / self.n if self.n else 0.0


def _allocate(total: int, clusters: Sequence[str]) -> dict[str, int]:
    base, remainder = divmod(total, len(clusters))
    return {
        cluster: base + (1 if position < remainder else 0)
        for position, cluster in enumerate(clusters)
    }


def plan_runs(models: Sequence[str], clusters: Sequence[str], now: datetime) -> list[CanaryRun]:
    """The runs due at ``now`` (call once per hour)."""
    runs: list[CanaryRun] = []
    for model in models:
        runs.append(
            CanaryRun(
                model_id=model,
                cluster_id=None,
                cadence="pulse",
                n=CADENCE_N["pulse"],
                scheduled_at=now,
            )
        )
        if now.hour == DAILY_HOUR_UTC and clusters:
            for cluster, n in _allocate(CADENCE_N["daily"], clusters).items():
                runs.append(
                    CanaryRun(
                        model_id=model,
                        cluster_id=cluster,
                        cadence="daily",
                        n=n,
                        scheduled_at=now,
                    )
                )
        if now.hour == DAILY_HOUR_UTC and now.weekday() == WEEKLY_WEEKDAY and clusters:
            for cluster, n in _allocate(CADENCE_N["weekly"], clusters).items():
                runs.append(
                    CanaryRun(
                        model_id=model,
                        cluster_id=cluster,
                        cadence="weekly",
                        n=n,
                        scheduled_at=now,
                    )
                )
    return runs
