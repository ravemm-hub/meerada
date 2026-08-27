"""Statistics for canary and drift detection (SPEC §6.1, §6.3).

This module is the credibility of the product: no shortcuts, no hardcoded
thresholds. Wilson intervals live in ``handover.metrics.core`` (single source);
here: normal helpers, the two-proportion sample-size/power calculator, a
two-proportion z-test, one-sided CUSUM, and Benjamini-Hochberg FDR.

Note on §6.1's practical table (70/150/570/3400 for a 0.90 base): those numbers
correspond to a ONE-SIDED alpha of 0.05, so that is the default here;
``two_sided=True`` gives the textbook z_{alpha/2} version.
"""

import math
from collections.abc import Sequence

from handover.metrics.core import newcombe_diff_ci, wilson_interval

__all__ = [
    "Cusum",
    "benjamini_hochberg",
    "newcombe_diff_ci",
    "normal_cdf",
    "normal_ppf",
    "power_two_proportions",
    "sample_size_two_proportions",
    "two_proportion_p_value",
    "wilson_interval",
]

# Acklam's rational approximation for the inverse normal CDF.
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
_P_LOW = 0.02425


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_ppf(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    if p < _P_LOW:
        q = math.sqrt(-2 * math.log(p))
        return (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1
        )
    if p > 1 - _P_LOW:
        return -normal_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (
        (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5])
        * q
        / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1)
    )


def sample_size_two_proportions(
    p_base: float,
    delta: float,
    *,
    alpha: float = 0.05,
    power: float = 0.8,
    two_sided: bool = False,
) -> int:
    """n per arm to detect a drop of `delta` from `p_base` (SPEC §6.1 formula)."""
    if not 0 < delta < p_base <= 1:
        raise ValueError("need 0 < delta < p_base <= 1")
    p1, p2 = p_base, p_base - delta
    z_alpha = normal_ppf(1 - alpha / 2) if two_sided else normal_ppf(1 - alpha)
    z_beta = normal_ppf(power)
    p_bar = (p1 + p2) / 2
    numerator = (
        z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
        + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2
    return math.ceil(numerator / delta**2)


def power_two_proportions(
    n: int,
    p_base: float,
    delta: float,
    *,
    alpha: float = 0.05,
    two_sided: bool = False,
) -> float:
    """Probability of detecting a drop of `delta` with n per arm."""
    p1, p2 = p_base, p_base - delta
    z_alpha = normal_ppf(1 - alpha / 2) if two_sided else normal_ppf(1 - alpha)
    p_bar = (p1 + p2) / 2
    se_null = math.sqrt(2 * p_bar * (1 - p_bar) / n)
    se_alt = math.sqrt((p1 * (1 - p1) + p2 * (1 - p2)) / n)
    return normal_cdf((delta - z_alpha * se_null) / se_alt)


def two_proportion_p_value(
    successes_a: int, n_a: int, successes_b: int, n_b: int, *, two_sided: bool = True
) -> float:
    """Pooled two-proportion z-test p-value (feeds Benjamini-Hochberg in drift)."""
    if n_a == 0 or n_b == 0:
        raise ValueError("both samples must be non-empty")
    p_a, p_b = successes_a / n_a, successes_b / n_b
    pooled = (successes_a + successes_b) / (n_a + n_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    if se == 0:
        return 1.0
    z = (p_a - p_b) / se
    tail = 1 - normal_cdf(abs(z))
    return min(1.0, 2 * tail if two_sided else tail)


class Cusum:
    """One-sided tabular CUSUM for detecting a downward shift in a rate.

    S = max(0, S + (target - x) - k); alarm when S > h. With k = drift/2 the
    chart is tuned to detect a drop of `drift` quickly while staying quiet
    under the null.
    """

    def __init__(self, target: float, drift: float, threshold: float) -> None:
        self.target = target
        self.k = drift / 2
        self.h = threshold
        self.statistic = 0.0

    def update(self, observed: float) -> bool:
        self.statistic = max(0.0, self.statistic + (self.target - observed) - self.k)
        return self.statistic > self.h

    def reset(self) -> None:
        self.statistic = 0.0


def benjamini_hochberg(p_values: Sequence[float], q: float = 0.05) -> list[bool]:
    """FDR control across all model x cluster comparisons (SPEC §6.3 rule 4).

    Returns a rejected-flag per input p-value. Without this, 480 daily
    comparisons at alpha=0.05 would produce ~24 false alerts a day.
    """
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    cutoff_rank = 0
    for rank, index in enumerate(order, start=1):
        if p_values[index] <= rank / m * q:
            cutoff_rank = rank
    rejected = [False] * m
    for rank, index in enumerate(order, start=1):
        if rank <= cutoff_rank:
            rejected[index] = True
    return rejected
