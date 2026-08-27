"""Core metrics (SPEC §4.1): success rate, CPAT, TTAT, attempts-per-win.

The denominator is successful tasks; the numerator includes the cost of
failures — that is what makes the number honest. Tasks graded "unknown" are
excluded from every computation (SPEC §3.2 rule 4). Zero successes yields
None, never infinity.
"""

import math
from collections.abc import Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from handover.schema.task import Task


class Proportion(BaseModel):
    """A rate with its sample size and Wilson 95% confidence interval (P3 rule)."""

    model_config = ConfigDict(frozen=True)

    value: float | None
    n: int
    ci_low: float | None
    ci_high: float | None


class PerWinMoney(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: Decimal | None
    n_successes: int
    n_tasks: int


class PerWinFloat(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float | None
    n_successes: int
    n_tasks: int


class CoreMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    n_tasks: int
    n_verified: int
    n_unknown: int
    unknown_rate: Proportion
    success_rate: Proportion
    cpat_usd: PerWinMoney
    ttat_seconds: PerWinFloat
    attempts_per_win: PerWinFloat


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be within [0, n]")
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    # Clamp to [0, 1] and force the interval to contain p despite float error.
    return min(p, max(0.0, centre - margin)), max(p, min(1.0, centre + margin))


def newcombe_diff_ci(
    successes_new: int, n_new: int, successes_old: int, n_old: int, z: float = 1.96
) -> tuple[float, float]:
    """Wilson-based (Newcombe) CI for delta = p_new - p_old. Negative = a drop."""
    p_new, p_old = successes_new / n_new, successes_old / n_old
    low_new, high_new = wilson_interval(successes_new, n_new, z)
    low_old, high_old = wilson_interval(successes_old, n_old, z)
    delta = p_new - p_old
    lower = delta - math.sqrt((p_new - low_new) ** 2 + (high_old - p_old) ** 2)
    upper = delta + math.sqrt((high_new - p_new) ** 2 + (p_old - low_old) ** 2)
    return max(-1.0, lower), min(1.0, upper)


def proportion(successes: int, n: int) -> Proportion:
    if n == 0:
        return Proportion(value=None, n=0, ci_low=None, ci_high=None)
    ci_low, ci_high = wilson_interval(successes, n)
    return Proportion(value=successes / n, n=n, ci_low=ci_low, ci_high=ci_high)


def compute_core(tasks: Sequence[Task]) -> CoreMetrics:
    verified = [task for task in tasks if task.verification_grade != "unknown"]
    wins = sum(1 for task in verified if task.succeeded)
    n_verified = len(verified)

    total_cost = sum((task.total_cost_usd for task in verified), Decimal("0"))
    total_wall_s = sum(task.total_wall_ms for task in verified) / 1000.0
    total_attempts = sum(task.attempts for task in verified)

    return CoreMetrics(
        n_tasks=len(tasks),
        n_verified=n_verified,
        n_unknown=len(tasks) - n_verified,
        unknown_rate=proportion(len(tasks) - n_verified, len(tasks)),
        success_rate=proportion(wins, n_verified),
        cpat_usd=PerWinMoney(
            value=None if wins == 0 else total_cost / wins,
            n_successes=wins,
            n_tasks=n_verified,
        ),
        ttat_seconds=PerWinFloat(
            value=None if wins == 0 else total_wall_s / wins,
            n_successes=wins,
            n_tasks=n_verified,
        ),
        attempts_per_win=PerWinFloat(
            value=None if wins == 0 else total_attempts / wins,
            n_successes=wins,
            n_tasks=n_verified,
        ),
    )


def by_model(tasks: Sequence[Task]) -> dict[str, CoreMetrics]:
    """Group by the model that finished the task (last in models_used)."""
    groups: dict[str, list[Task]] = {}
    for task in tasks:
        groups.setdefault(task.models_used[-1], []).append(task)
    return {model: compute_core(group) for model, group in sorted(groups.items())}
