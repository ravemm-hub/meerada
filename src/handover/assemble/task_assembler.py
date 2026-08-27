"""Task assembly (SPEC §3.2): group retry attempts into one accounting unit.

Rule 1: an explicit client task_id always wins.
Rule 2: otherwise attempts chain into one task when they share a session and a
system-prompt template, start less than 120s after the previous attempt ended,
and their inputs overlap by more than 0.8.
Rule 3: a task succeeded if at least one attempt verified as pass.
Rule 4: a task with no verification signal is graded "unknown" (metrics exclude it).
"""

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from handover.schema.task import Task, TaskTokens
from handover.schema.trace import Trace

GAP_SECONDS = 120
MIN_INPUT_OVERLAP = 0.8

_GRADE_PRECEDENCE: dict[str, int] = {"measured": 0, "derived": 1, "declared": 2}


class AttemptRecord(BaseModel):
    """One normalized attempt plus the in-tenant context the heuristic needs.

    ``input_shingles`` are salted hashes of input n-grams, computed in-tenant so
    Jaccard overlap can be estimated without content. When either side lacks
    them, attempts that already share a session, a template and a <120s gap are
    treated as the same task — retry inputs usually differ slightly (appended
    feedback), so exact-fingerprint equality would over-split retries.
    """

    model_config = ConfigDict(frozen=True)

    trace: Trace
    session_id: str | None = None
    explicit_task_id: UUID | None = None
    input_shingles: frozenset[str] | None = None


def _overlap(a: AttemptRecord, b: AttemptRecord) -> float:
    if a.input_shingles is None or b.input_shingles is None:
        return 1.0
    union = a.input_shingles | b.input_shingles
    if not union:
        return 1.0
    return len(a.input_shingles & b.input_shingles) / len(union)


def _same_task(prev: AttemptRecord, record: AttemptRecord) -> bool:
    gap = (record.trace.ts_start - prev.trace.ts_end).total_seconds()
    same_template = (
        prev.trace.input_shape.system_prompt_fingerprint
        == record.trace.input_shape.system_prompt_fingerprint
    )
    return same_template and gap < GAP_SECONDS and _overlap(prev, record) > MIN_INPUT_OVERLAP


def _heuristic_groups(records: Sequence[AttemptRecord]) -> list[list[AttemptRecord]]:
    groups: list[list[AttemptRecord]] = []
    by_session: dict[str, list[AttemptRecord]] = {}
    for record in records:
        if record.session_id is None:
            groups.append([record])  # no session context: never merged by heuristic
        else:
            by_session.setdefault(record.session_id, []).append(record)

    for session_records in by_session.values():
        session_records.sort(key=lambda r: r.trace.ts_start)
        current: list[AttemptRecord] = []
        for record in session_records:
            if current and _same_task(current[-1], record):
                current.append(record)
            else:
                if current:
                    groups.append(current)
                current = [record]
        if current:
            groups.append(current)
    return groups


def _build_task(group: Sequence[AttemptRecord], task_id: UUID) -> Task:
    traces = [r.trace for r in sorted(group, key=lambda r: r.trace.ts_start)]
    verified = [t for t in traces if t.verification.status != "unknown"]

    grade: Literal["measured", "derived", "declared", "unknown"]
    if not verified:
        grade = "unknown"
    else:
        strongest = min(verified, key=lambda t: _GRADE_PRECEDENCE[t.verification.evidence_grade])
        grade = strongest.verification.evidence_grade

    models: list[str] = []
    for trace in traces:
        if trace.model_id not in models:
            models.append(trace.model_id)

    return Task(
        task_id=task_id,
        tenant_id=traces[0].tenant_id,
        attempts=len(traces),
        succeeded=any(t.verification.status == "pass" for t in traces),
        first_attempt_success=traces[0].verification.status == "pass",
        total_cost_usd=sum((t.cost_usd for t in traces), Decimal("0")),
        total_wall_ms=sum(t.latency.total_ms for t in traces),
        total_tokens=TaskTokens(
            input=sum(t.tokens.input for t in traces),
            output=sum(t.tokens.output for t in traces),
            reasoning=sum(t.tokens.reasoning for t in traces),
        ),
        models_used=tuple(models),
        verification_grade=grade,
    )


def assemble_grouped(records: Iterable[AttemptRecord]) -> list[tuple[Task, tuple[Trace, ...]]]:
    """Assemble tasks and keep each task paired with its ordered traces."""
    explicit: dict[UUID, list[AttemptRecord]] = {}
    implicit: list[AttemptRecord] = []
    for record in records:
        if record.explicit_task_id is not None:
            explicit.setdefault(record.explicit_task_id, []).append(record)
        else:
            implicit.append(record)

    groups: list[tuple[list[AttemptRecord], UUID]] = [
        (group, task_id) for task_id, group in explicit.items()
    ]
    groups.extend((group, group[0].trace.task_id) for group in _heuristic_groups(implicit))

    result: list[tuple[Task, tuple[Trace, ...]]] = []
    for group, task_id in groups:
        ordered = sorted(group, key=lambda r: r.trace.ts_start)
        result.append((_build_task(ordered, task_id), tuple(r.trace for r in ordered)))
    return result


def assemble(records: Iterable[AttemptRecord]) -> list[Task]:
    return [task for task, _ in assemble_grouped(records)]
