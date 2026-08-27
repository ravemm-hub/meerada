"""The gap report (SPEC §7.4) — the table that sells the product.

Per cluster: cost share, from/to pass rates, deltas for pass, cost and
latency, and a PASS/BLOCK verdict. BLOCK only when the drop is statistically
real: the Newcombe CI of the delta excludes zero AND |delta| exceeds the
minimum effect (§6.3 conditions 1-2; windows/FDR apply to canaries, not to a
one-shot comparison). Clusters the replay never reached (budget stop) are
reported separately — never guessed.

Engineer-days for a blocked cluster is a labelled heuristic:
1.5 base + 0.5 per edge-case signature + 8 x cost share, clamped to [1, 15].
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from handover.cluster.extractor import Clustering
from handover.metrics import CoreMetrics, newcombe_diff_ci
from handover.replay.runner import ReplayReport

MIN_EFFECT_POINTS = 5.0


class ClusterGap(BaseModel):
    model_config = ConfigDict(frozen=True)

    cluster_id: str
    label: str | None
    share_of_cost: float
    from_pass: float
    to_pass: float
    delta_points: float  # (to - from) x 100
    ci_low_points: float
    ci_high_points: float
    delta_cost_pct: float | None
    delta_latency_pct: float | None
    n_from: int
    n_to: int
    verdict: str  # PASS | BLOCK
    engineer_days: float | None  # only for BLOCK


class GapReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_model: str
    to_model: str
    clusters: tuple[ClusterGap, ...]
    n_pass: int
    n_block: int
    n_no_data: int  # clusters the replay never reached
    total_engineer_days: float


def _engineer_days(edge_cases: int, share_of_cost: float) -> float:
    return round(min(15.0, max(1.0, 1.5 + 0.5 * edge_cases + 8.0 * share_of_cost)), 1)


def build_gap_report(
    clustering: Clustering,
    baselines: Mapping[str, CoreMetrics],
    replay_report: ReplayReport,
    from_model: str,
    *,
    edge_case_counts: Mapping[str, int] | None = None,
    min_effect_points: float = MIN_EFFECT_POINTS,
) -> GapReport:
    by_cluster: dict[str, list[bool]] = {}
    for outcome in replay_report.outcomes:
        if outcome.passed is not None:
            by_cluster.setdefault(outcome.cluster_id, []).append(outcome.passed)

    gaps: list[ClusterGap] = []
    n_no_data = 0
    for cluster in clustering.clusters:
        baseline = baselines.get(cluster.cluster_id)
        verdicts = by_cluster.get(cluster.cluster_id, [])
        if baseline is None or baseline.success_rate.value is None or not verdicts:
            n_no_data += 1
            continue

        n_from = baseline.success_rate.n
        s_from = round(baseline.success_rate.value * n_from)
        n_to = len(verdicts)
        s_to = sum(verdicts)

        ci_low, ci_high = newcombe_diff_ci(s_to, n_to, s_from, n_from)
        delta_points = (s_to / n_to - s_from / n_from) * 100

        significant_drop = ci_high < 0 and abs(delta_points) > min_effect_points
        verdict = "BLOCK" if significant_drop else "PASS"

        to_cpat = replay_cluster_cpat(replay_report, cluster.cluster_id) if s_to else None
        from_cpat = baseline.cpat_usd.value
        delta_cost = (
            float((to_cpat - from_cpat) / from_cpat) if to_cpat is not None and from_cpat else None
        )

        latencies = [
            o.latency_ms
            for o in replay_report.outcomes
            if o.cluster_id == cluster.cluster_id and o.passed is not None and not o.deduped
        ]
        from_ttat = baseline.ttat_seconds.value
        delta_latency = (
            (sum(latencies) / len(latencies) / 1000 - from_ttat) / from_ttat
            if latencies and from_ttat
            else None
        )

        edge_count = (edge_case_counts or {}).get(cluster.cluster_id, 0)
        gaps.append(
            ClusterGap(
                cluster_id=cluster.cluster_id,
                label=cluster.label,
                share_of_cost=cluster.share_of_cost,
                from_pass=s_from / n_from,
                to_pass=s_to / n_to,
                delta_points=round(delta_points, 1),
                ci_low_points=round(ci_low * 100, 1),
                ci_high_points=round(ci_high * 100, 1),
                delta_cost_pct=delta_cost,
                delta_latency_pct=delta_latency,
                n_from=n_from,
                n_to=n_to,
                verdict=verdict,
                engineer_days=(
                    _engineer_days(edge_count, cluster.share_of_cost)
                    if verdict == "BLOCK"
                    else None
                ),
            )
        )

    blocked = [g for g in gaps if g.verdict == "BLOCK"]
    return GapReport(
        from_model=from_model,
        to_model=replay_report.model_id,
        clusters=tuple(gaps),
        n_pass=len(gaps) - len(blocked),
        n_block=len(blocked),
        n_no_data=n_no_data,
        total_engineer_days=round(sum(g.engineer_days or 0 for g in blocked), 1),
    )


def replay_cluster_cpat(report: ReplayReport, cluster_id: str) -> Decimal | None:
    outcomes = [o for o in report.outcomes if o.cluster_id == cluster_id]
    wins = sum(1 for o in outcomes if o.passed)
    if not wins:
        return None
    total = sum((o.cost_usd for o in outcomes), Decimal("0"))
    return total / wins


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.0f}%"


def format_gap_report(report: GapReport) -> str:
    """Render the exact §7.4 table shape as fixed-width text."""
    header = (
        f"{'cluster':<22}{'share':>7}{'from':>7}{'to':>7}"
        f"{'Δpass':>8}{'Δcost':>8}{'Δlat':>7}  verdict"
    )
    rule = "─" * len(header)
    lines = [header, rule]
    for gap in report.clusters:
        name = (gap.label or gap.cluster_id)[:21]
        lines.append(
            f"{name:<22}{gap.share_of_cost * 100:>6.0f}%{gap.from_pass:>7.2f}"
            f"{gap.to_pass:>7.2f}{gap.delta_points:>+8.1f}{_pct(gap.delta_cost_pct):>8}"
            f"{_pct(gap.delta_latency_pct):>7}  {gap.verdict}"
        )
    lines.append(rule)
    total = report.n_pass + report.n_block
    lines.append(f"{report.n_pass}/{total} clusters pass. Blocks: {report.n_block}.")
    if report.n_block:
        lines.append(f"Estimated work: {report.total_engineer_days} engineer-days.")
    if report.n_no_data:
        lines.append(f"{report.n_no_data} clusters had no replay data (budget stop).")
    return "\n".join(lines)


def blocked_clusters(report: GapReport) -> Sequence[ClusterGap]:
    return [g for g in report.clusters if g.verdict == "BLOCK"]
