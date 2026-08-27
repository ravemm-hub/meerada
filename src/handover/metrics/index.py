"""The public three-axis score (SPEC §4.3).

Score(w) = w_q * norm(Quality) + w_s * norm(Speed) + w_v * norm(Value), with
Speed = 1/TTAT and Value = 1/CPAT log-normalized. Min-max normalization runs
WITHIN a cluster across models — never across clusters (hard SPEC rule).
A model's overall index score is the cost-share-weighted mean of its cluster
scores. Weights are user-facing sliders; defaults are (0.6, 0.2, 0.2).
"""

import math
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from handover.metrics.core import CoreMetrics


class Weights(BaseModel):
    model_config = ConfigDict(frozen=True)

    quality: float = 0.6
    speed: float = 0.2
    value: float = 0.2

    @model_validator(mode="after")
    def _sums_to_one(self) -> "Weights":
        if abs(self.quality + self.speed + self.value - 1.0) > 1e-6:
            raise ValueError("weights must sum to 1")
        return self


class AxisNorms(BaseModel):
    """Per-model normalized axes within one cluster (all in [0, 1])."""

    model_config = ConfigDict(frozen=True)

    cluster_id: str
    model_id: str
    quality: float
    speed: float
    value: float
    n_successes: int

    def score(self, weights: Weights) -> float:
        return 100.0 * (
            weights.quality * self.quality + weights.speed * self.speed + weights.value * self.value
        )


class IndexEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    score: float | None  # cost-share-weighted mean of cluster scores
    cluster_scores: dict[str, float]


def _minmax(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def cluster_axis_norms(
    cluster_id: str, metrics_by_model: Mapping[str, CoreMetrics]
) -> list[AxisNorms]:
    """Normalize the three axes across the models of ONE cluster."""
    eligible = [
        (model_id, metrics)
        for model_id, metrics in sorted(metrics_by_model.items())
        if metrics.success_rate.value is not None
        and metrics.cpat_usd.value
        and metrics.ttat_seconds.value
    ]
    if not eligible:
        return []
    quality = _minmax([m.success_rate.value or 0.0 for _, m in eligible])
    speed = _minmax([math.log(1.0 / (m.ttat_seconds.value or 1.0)) for _, m in eligible])
    value = _minmax([math.log(1.0 / float(m.cpat_usd.value or 1)) for _, m in eligible])
    return [
        AxisNorms(
            cluster_id=cluster_id,
            model_id=model_id,
            quality=quality[i],
            speed=speed[i],
            value=value[i],
            n_successes=metrics.cpat_usd.n_successes,
        )
        for i, (model_id, metrics) in enumerate(eligible)
    ]


def compute_index(
    per_cluster: Mapping[str, Mapping[str, CoreMetrics]],
    cost_shares: Mapping[str, float],
    weights: Weights | None = None,
) -> list[IndexEntry]:
    """Rank models across clusters. Sorted by score, best first."""
    weights = weights or Weights()
    norms = [
        norm
        for cluster_id, metrics_by_model in sorted(per_cluster.items())
        for norm in cluster_axis_norms(cluster_id, metrics_by_model)
    ]

    models = sorted({norm.model_id for norm in norms})
    entries = []
    for model_id in models:
        mine = [n for n in norms if n.model_id == model_id]
        cluster_scores = {n.cluster_id: round(n.score(weights), 1) for n in mine}
        total_share = sum(cost_shares.get(n.cluster_id, 0.0) for n in mine)
        score = (
            sum(n.score(weights) * cost_shares.get(n.cluster_id, 0.0) for n in mine) / total_share
            if total_share
            else None
        )
        entries.append(
            IndexEntry(
                model_id=model_id,
                score=None if score is None else round(score, 1),
                cluster_scores=cluster_scores,
            )
        )
    entries.sort(key=lambda e: e.score if e.score is not None else -1.0, reverse=True)
    return entries


def index_payload(
    per_cluster: Mapping[str, Mapping[str, CoreMetrics]],
    cost_shares: Mapping[str, float],
) -> dict[str, Any]:
    """JSON-safe payload of normalized axes for the static page's weight sliders."""
    norms = [
        norm.model_dump()
        for cluster_id, metrics_by_model in sorted(per_cluster.items())
        for norm in cluster_axis_norms(cluster_id, metrics_by_model)
    ]
    return {"norms": norms, "cost_shares": dict(cost_shares)}
