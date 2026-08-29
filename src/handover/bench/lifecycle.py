"""Grade lifecycle — how a model's public grade earns confidence over time.

A newly-discovered model is graded FAST on a small sample: a provisional grade
with a wide confidence interval, clearly labelled. As the canary keeps
sampling (SPEC §6.2 pulse -> daily -> weekly), the sample grows and the grade
tightens to confirmed. This is what makes the index near-real-time AND
trustworthy: never a bare number without its sample size, freshness and status.
"""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from handover.metrics.core import Proportion

GradeStatus = Literal["provisional", "confirmed", "stale"]

# n thresholds mirror the canary cadences: pulse(30) < provisional line < daily(600).
PROVISIONAL_MIN_N = 30
CONFIRMED_MIN_N = 600
STALE_AFTER = timedelta(hours=48)  # a confirmed grade older than this needs a refresh


class GradeCard(BaseModel):
    """One model's public grade with everything needed to trust it."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    score: float | None
    quality: Proportion  # success rate with Wilson CI
    n: int
    status: GradeStatus
    updated_at: datetime
    ci_width_points: float | None  # high-low of the quality CI, in points

    @property
    def is_publishable(self) -> bool:
        """Provisional grades may show (labelled); a grade below the provisional
        floor, or with no successes measured, must not be published as a rank."""
        return self.status != "stale" and self.n >= PROVISIONAL_MIN_N and self.score is not None


def classify(
    model_id: str,
    score: float | None,
    quality: Proportion,
    updated_at: datetime,
    now: datetime,
) -> GradeCard:
    n = quality.n
    if n < PROVISIONAL_MIN_N:
        status: GradeStatus = "provisional"
    elif n < CONFIRMED_MIN_N:
        status = "provisional"
    else:
        status = "stale" if now - updated_at > STALE_AFTER else "confirmed"

    ci_width = (
        None
        if quality.ci_low is None or quality.ci_high is None
        else round((quality.ci_high - quality.ci_low) * 100, 1)
    )
    return GradeCard(
        model_id=model_id,
        score=score,
        quality=quality,
        n=n,
        status=status,
        updated_at=updated_at,
        ci_width_points=ci_width,
    )


def next_cadence(card: GradeCard) -> Literal["pulse", "daily", "weekly", "hold"]:
    """What sampling a card needs next to advance its confidence.

    Provisional models are pushed to daily sampling to reach confirmed; stale
    confirmed models get a refresh; healthy confirmed models hold at weekly.
    """
    if card.status == "provisional":
        return "daily"
    if card.status == "stale":
        return "daily"
    return "weekly"
