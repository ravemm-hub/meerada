"""Drift detection enforcing ALL FOUR §6.3 alert conditions.

alert = TRUE if and only if:
  (1) the Newcombe CI of the delta vs baseline excludes zero (a real drop),
  (2) |delta| > min_effect (default 5 points),
  (3) the drop holds in two consecutive windows OR CUSUM crossed its threshold,
  (4) it survives Benjamini-Hochberg FDR across ALL model x cluster pairs.

Alerts render exactly the §6.4 format. Improvements never alert — this
detector watches for degradation.
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from handover.canary.scheduler import WindowStat
from handover.canary.stats import (
    Cusum,
    benjamini_hochberg,
    benjamini_hochberg_qvalues,
    two_proportion_p_value,
)
from handover.metrics.core import newcombe_diff_ci

MIN_EFFECT_POINTS = 5.0
CUSUM_THRESHOLD = 0.5

PairKey = tuple[str, str]  # (model_id, cluster_id)


class Baseline(BaseModel):
    model_config = ConfigDict(frozen=True)

    successes: int
    n: int

    @property
    def rate(self) -> float:
        return self.successes / self.n


class DriftAlert(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    cluster_id: str
    cluster_label: str
    baseline_rate: float
    current_rate: float
    delta_points: float
    ci_low_points: float
    ci_high_points: float
    n: int
    confirmed_windows: int  # 2 when two consecutive windows confirmed
    cusum_crossed: bool
    q_value: float
    first_observed: str  # ISO-ish "YYYY-MM-DD HH:MMZ"

    def render(self) -> str:
        """Exactly the SPEC §6.4 alert format."""
        confirmation = (
            f"confirmed over {self.confirmed_windows} windows"
            if self.confirmed_windows >= 2
            else "CUSUM threshold crossed"
        )
        return (
            f'Model {self.model_id} · cluster "{self.cluster_label}"\n'
            f"pass rate: {self.baseline_rate:.2f} → {self.current_rate:.2f}   "
            f"(Δ = {self.delta_points:+.1f} pts, "
            f"CI95: [{self.ci_low_points:.1f}, {self.ci_high_points:.1f}])\n"
            f"n = {self.n} · {confirmation} · FDR-adjusted q = {self.q_value:.3f}\n"
            f"first observed: {self.first_observed}"
        )


def _window_is_drop(window: WindowStat, baseline: Baseline, min_effect_points: float) -> bool:
    """Conditions (1) and (2) for a single window vs the baseline."""
    _, ci_high = newcombe_diff_ci(window.successes, window.n, baseline.successes, baseline.n)
    delta_points = (window.rate - baseline.rate) * 100
    return ci_high < 0 and abs(delta_points) > min_effect_points


def detect_drift(
    baselines: Mapping[PairKey, Baseline],
    windows: Mapping[PairKey, Sequence[WindowStat]],
    *,
    cluster_labels: Mapping[str, str] | None = None,
    min_effect_points: float = MIN_EFFECT_POINTS,
    q: float = 0.05,
    cusum_threshold: float = CUSUM_THRESHOLD,
) -> list[DriftAlert]:
    """Evaluate every pair. ``windows`` must be time-ordered, oldest first."""
    pairs = [key for key in windows if key in baselines and windows[key]]

    # Condition (4) runs across ALL pairs, not only the suspicious ones.
    p_values = [
        two_proportion_p_value(
            windows[key][-1].successes,
            windows[key][-1].n,
            baselines[key].successes,
            baselines[key].n,
        )
        for key in pairs
    ]
    survives_fdr = benjamini_hochberg(p_values, q=q)
    q_values = benjamini_hochberg_qvalues(p_values)

    alerts: list[DriftAlert] = []
    for index, key in enumerate(pairs):
        baseline = baselines[key]
        history = list(windows[key])
        current = history[-1]

        if not _window_is_drop(current, baseline, min_effect_points):  # (1) + (2)
            continue

        previous_confirms = len(history) >= 2 and _window_is_drop(
            history[-2], baseline, min_effect_points
        )
        cusum = Cusum(
            target=baseline.rate, drift=min_effect_points / 100, threshold=cusum_threshold
        )
        cusum_crossed = any(cusum.update(window.rate) for window in history)
        if not (previous_confirms or cusum_crossed):  # (3)
            continue

        if not survives_fdr[index]:  # (4)
            continue

        first = history[-2] if previous_confirms else current
        ci_low, ci_high = newcombe_diff_ci(
            current.successes, current.n, baseline.successes, baseline.n
        )
        model_id, cluster_id = key
        alerts.append(
            DriftAlert(
                model_id=model_id,
                cluster_id=cluster_id,
                cluster_label=(cluster_labels or {}).get(cluster_id, cluster_id),
                baseline_rate=baseline.rate,
                current_rate=current.rate,
                delta_points=round((current.rate - baseline.rate) * 100, 1),
                ci_low_points=round(ci_low * 100, 1),
                ci_high_points=round(ci_high * 100, 1),
                n=current.n,
                confirmed_windows=2 if previous_confirms else 1,
                cusum_crossed=cusum_crossed,
                q_value=round(q_values[index], 3),
                first_observed=first.ts.strftime("%Y-%m-%d %H:%MZ"),
            )
        )
    return alerts
