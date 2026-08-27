"""Golden set builder (SPEC §7.2 step 5).

Only grade-A (measured) verified successes enter — no compromises. Size is
max(30, 3% of cluster), stratified by cost and by output length. Cases carry
tenant-local content POINTERS only; content is never inlined.
"""

import math
from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from handover.metrics.waste import TaskTraces
from handover.schema.trace import Trace

MINIMUM = 30
FRACTION = 0.03
_COST_STRATA = 3


class GoldenCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: UUID  # the task id
    cluster_id: str
    input_ref: str  # tenant-local pointer, e.g. trace://<id>/input
    expected_ref: str  # tenant-local pointer, e.g. trace://<id>/output
    verifier_spec: str
    cost_usd: Decimal
    output_n_chars: int


def _passing_trace(item: TaskTraces) -> Trace | None:
    for trace in reversed(item.traces):
        if trace.verification.status == "pass" and trace.verification.evidence_grade == "measured":
            return trace
    return None


def _spread(
    candidates: list[tuple[TaskTraces, Trace]], quota: int
) -> list[tuple[TaskTraces, Trace]]:
    """Evenly spaced picks over a sorted list — deterministic stratification."""
    if quota >= len(candidates):
        return candidates
    step = len(candidates) / quota
    return [candidates[min(len(candidates) - 1, int(i * step))] for i in range(quota)]


def build_goldset(
    cluster_id: str,
    items: Sequence[TaskTraces],
    *,
    minimum: int = MINIMUM,
    fraction: float = FRACTION,
) -> tuple[GoldenCase, ...]:
    eligible: list[tuple[TaskTraces, Trace]] = []
    for item in items:
        trace = _passing_trace(item)
        if trace is not None:
            eligible.append((item, trace))

    target = max(minimum, math.ceil(fraction * len(items)))
    if len(eligible) <= target:
        chosen = eligible
    else:
        # Stratify by cost (terciles of the cost-sorted list), then spread each
        # stratum by output length so both dimensions are covered.
        by_cost = sorted(eligible, key=lambda pair: pair[0].task.total_cost_usd)
        stratum_size = math.ceil(len(by_cost) / _COST_STRATA)
        chosen = []
        for i in range(_COST_STRATA):
            stratum = by_cost[i * stratum_size : (i + 1) * stratum_size]
            stratum.sort(key=lambda pair: pair[1].output_shape.n_chars)
            quota = target // _COST_STRATA + (1 if i < target % _COST_STRATA else 0)
            chosen.extend(_spread(stratum, quota))

    return tuple(
        GoldenCase(
            case_id=item.task.task_id,
            cluster_id=cluster_id,
            input_ref=f"trace://{trace.trace_id}/input",
            expected_ref=f"trace://{trace.trace_id}/output",
            verifier_spec=trace.verification.signal,
            cost_usd=item.task.total_cost_usd,
            output_n_chars=trace.output_shape.n_chars,
        )
        for item, trace in chosen
    )
