"""Tool policy extraction per cluster (SPEC §7.2 step 3).

From successful attempts only: which tools are used and how often, the
transition graph between consecutive calls, and frequency-based ordering
constraints ("B is never called before A") with support-derived confidence.
"""

from collections import Counter
from collections.abc import Sequence
from itertools import pairwise

from pydantic import BaseModel, ConfigDict

from handover.metrics.waste import TaskTraces
from handover.schema.trace import Trace

MIN_CONSTRAINT_SUPPORT = 3


class ToolTransition(BaseModel):
    model_config = ConfigDict(frozen=True)

    src: str
    dst: str
    count: int
    probability: float  # of all transitions leaving src


class OrderingConstraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    before: str
    after: str
    support: int  # sequences where both tools appear
    confidence: float  # support / (support + 1) — rule of succession


class ToolPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    cluster_id: str
    n_sequences: int
    tool_frequencies: dict[str, float]  # share of successful tasks using the tool
    transitions: tuple[ToolTransition, ...]
    constraints: tuple[OrderingConstraint, ...]


def _success_sequences(items: Sequence[TaskTraces]) -> list[list[str]]:
    sequences = []
    for item in items:
        if not item.task.succeeded or item.task.verification_grade == "unknown":
            continue
        trace: Trace | None = next(
            (t for t in reversed(item.traces) if t.verification.status == "pass"), None
        )
        if trace is not None:
            sequences.append([call.name for call in trace.tool_calls])
    return sequences


def infer_tool_policy(cluster_id: str, items: Sequence[TaskTraces]) -> ToolPolicy:
    sequences = _success_sequences(items)
    n = len(sequences)

    usage: Counter[str] = Counter()
    transition_counts: Counter[tuple[str, str]] = Counter()
    for sequence in sequences:
        for tool in set(sequence):
            usage[tool] += 1
        for src, dst in pairwise(sequence):
            transition_counts[(src, dst)] += 1

    out_totals: Counter[str] = Counter()
    for (src, _), count in transition_counts.items():
        out_totals[src] += count
    transitions = tuple(
        ToolTransition(src=src, dst=dst, count=count, probability=count / out_totals[src])
        for (src, dst), count in sorted(
            transition_counts.items(), key=lambda kv: kv[1], reverse=True
        )
    )

    # Ordering constraints: for every ordered pair (a, b) present together in
    # enough sequences, a "a before b" constraint holds only when the first
    # occurrence of a precedes the first occurrence of b in EVERY co-occurrence.
    co_occurrence: Counter[tuple[str, str]] = Counter()
    violations: set[tuple[str, str]] = set()
    for sequence in sequences:
        first_seen: dict[str, int] = {}
        for position, tool in enumerate(sequence):
            first_seen.setdefault(tool, position)
        tools = sorted(first_seen)
        for a in tools:
            for b in tools:
                if a == b:
                    continue
                co_occurrence[(a, b)] += 1
                if first_seen[a] >= first_seen[b]:
                    violations.add((a, b))

    constraints = tuple(
        sorted(
            (
                OrderingConstraint(
                    before=a,
                    after=b,
                    support=support,
                    confidence=support / (support + 1),
                )
                for (a, b), support in co_occurrence.items()
                if support >= MIN_CONSTRAINT_SUPPORT and (a, b) not in violations
            ),
            key=lambda c: (-c.support, c.before, c.after),
        )
    )

    return ToolPolicy(
        cluster_id=cluster_id,
        n_sequences=n,
        tool_frequencies={tool: count / n for tool, count in sorted(usage.items())} if n else {},
        transitions=transitions,
        constraints=constraints,
    )
