"""Output contract inference per cluster (SPEC §7.2 steps 2 and 4).

Everything here derives from successful attempts only. The base contract is
metadata-only (schema fingerprints, output shapes, lengths). Field-level union
with frequencies needs content, which never leaves the tenant — so it is
computed only when the caller injects an in-tenant ``output_loader``.

Edge cases (step 4): successful tasks that deviated from the contract, grouped
by deviation signature and ranked by frequency x cost.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from handover.metrics.waste import TaskTraces
from handover.schema.trace import Trace

OutputLoader = Callable[[Trace], object | None]


class LengthDistribution(BaseModel):
    model_config = ConfigDict(frozen=True)

    p10: int
    p50: int
    p90: int


class FieldStat(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    presence: float  # share of successful JSON outputs containing the field
    types: tuple[str, ...]


class OutputContract(BaseModel):
    model_config = ConfigDict(frozen=True)

    cluster_id: str
    n_successes: int
    type_shares: dict[str, float]
    dominant_type: str
    dominant_schema_fingerprint: str | None
    dominant_schema_share: float
    json_valid_rate: float
    length: LengthDistribution
    fields: tuple[FieldStat, ...] = ()


class EdgeCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    signature: str
    n_tasks: int
    total_cost_usd: Decimal
    example_task_ids: tuple[UUID, ...]


def _successes(items: Sequence[TaskTraces]) -> list[tuple[TaskTraces, Trace]]:
    pairs = []
    for item in items:
        if not item.task.succeeded or item.task.verification_grade == "unknown":
            continue
        for trace in reversed(item.traces):
            if trace.verification.status == "pass":
                pairs.append((item, trace))
                break
    return pairs


def _percentile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    index = min(len(sorted_values) - 1, int(q * len(sorted_values)))
    return sorted_values[index]


def infer_contract(
    cluster_id: str,
    items: Sequence[TaskTraces],
    *,
    output_loader: OutputLoader | None = None,
) -> OutputContract:
    pairs = _successes(items)
    n = len(pairs)
    traces = [trace for _, trace in pairs]

    type_counts = Counter(t.output_shape.type for t in traces)
    schema_counts = Counter(
        t.output_shape.schema_fingerprint
        for t in traces
        if t.output_shape.schema_fingerprint is not None
    )
    dominant_schema, dominant_schema_n = (None, 0)
    if schema_counts:
        dominant_schema, dominant_schema_n = schema_counts.most_common(1)[0]

    lengths = sorted(t.output_shape.n_chars for t in traces)

    fields: tuple[FieldStat, ...] = ()
    if output_loader is not None and n:
        presence: Counter[str] = Counter()
        types: dict[str, set[str]] = {}
        n_loaded = 0
        for trace in traces:
            value = output_loader(trace)
            if not isinstance(value, dict):
                continue
            n_loaded += 1
            for key, field_value in value.items():
                presence[str(key)] += 1
                types.setdefault(str(key), set()).add(type(field_value).__name__)
        if n_loaded:
            fields = tuple(
                FieldStat(
                    name=name,
                    presence=count / n_loaded,
                    types=tuple(sorted(types[name])),
                )
                for name, count in sorted(presence.items())
            )

    return OutputContract(
        cluster_id=cluster_id,
        n_successes=n,
        type_shares={k: v / n for k, v in type_counts.items()} if n else {},
        dominant_type=type_counts.most_common(1)[0][0] if n else "text",
        dominant_schema_fingerprint=dominant_schema,
        dominant_schema_share=dominant_schema_n / n if n else 0.0,
        json_valid_rate=(sum(1 for t in traces if t.output_shape.json_valid) / n if n else 0.0),
        length=LengthDistribution(
            p10=_percentile(lengths, 0.10),
            p50=_percentile(lengths, 0.50),
            p90=_percentile(lengths, 0.90),
        ),
        fields=fields,
    )


def _deviations(trace: Trace, contract: OutputContract) -> list[str]:
    found = []
    if trace.output_shape.type != contract.dominant_type:
        found.append("type_mismatch")
    if (
        contract.dominant_schema_fingerprint is not None
        and trace.output_shape.schema_fingerprint is not None
        and trace.output_shape.schema_fingerprint != contract.dominant_schema_fingerprint
    ):
        found.append("schema_mismatch")
    if (
        not contract.length.p10
        <= trace.output_shape.n_chars
        <= max(contract.length.p90, contract.length.p10)
    ):
        found.append("length_outlier")
    return found


def find_edge_cases(items: Sequence[TaskTraces], contract: OutputContract) -> tuple[EdgeCase, ...]:
    """Successful tasks that deviated from the contract yet still passed —
    exactly the cases that break on migration. Ranked by frequency x cost."""
    groups: dict[str, list[TaskTraces]] = {}
    for item, trace in _successes(items):
        for signature in _deviations(trace, contract):
            groups.setdefault(signature, []).append(item)

    cases = [
        EdgeCase(
            signature=signature,
            n_tasks=len(members),
            total_cost_usd=sum((m.task.total_cost_usd for m in members), Decimal("0")),
            example_task_ids=tuple(m.task.task_id for m in members[:3]),
        )
        for signature, members in groups.items()
    ]
    cases.sort(key=lambda c: c.n_tasks * c.total_cost_usd, reverse=True)
    return tuple(cases)
