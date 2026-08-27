"""T4 tests: single success, retry-then-success, all-failed, unknown, and the
grouping rules (explicit id, session gap, template, input overlap)."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from handover.assemble import AttemptRecord, assemble
from handover.schema.trace import (
    InputShape,
    Latency,
    OutputShape,
    Tokens,
    Trace,
    Verification,
)

TENANT = uuid4()
T0 = datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC)


def fp(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


def make_trace(
    *,
    start_s: int,
    duration_s: int = 30,
    status: Literal["pass", "fail", "unknown"] = "pass",
    grade: Literal["measured", "derived", "declared"] = "measured",
    template: str = "template-1",
    model: str = "model-a",
    cost: str = "0.10",
) -> Trace:
    start = T0 + timedelta(seconds=start_s)
    return Trace(
        trace_id=uuid4(),
        tenant_id=TENANT,
        task_id=uuid4(),
        attempt_no=1,
        ts_start=start,
        ts_end=start + timedelta(seconds=duration_s),
        provider="anthropic",
        model_id=model,
        model_version_hint="unknown",
        endpoint_region="unknown",
        tokens=Tokens(input=100, input_cached=0, output=50, reasoning=10),
        cost_usd=Decimal(cost),
        latency=Latency(ttft_ms=500, total_ms=duration_s * 1000),
        input_shape=InputShape(
            n_messages=2,
            n_chars=500,
            has_attachments=False,
            system_prompt_fingerprint=fp(template),
            input_fingerprint=fp(f"input-{start_s}"),
        ),
        output_shape=OutputShape(
            type="text",
            n_chars=100,
            json_valid=False,
            schema_fingerprint=None,
            has_code_block=False,
            n_code_blocks=0,
        ),
        verification=Verification(
            status=status,
            method="programmatic",
            signal="test_exit_code" if status != "unknown" else "none",
            confidence=1.0 if status != "unknown" else 0.0,
            evidence_grade=grade if status != "unknown" else "declared",
        ),
    )


def rec(
    trace: Trace,
    session: str | None = "s-1",
    task_id: UUID | None = None,
    shingles: frozenset[str] | None = None,
) -> AttemptRecord:
    return AttemptRecord(
        trace=trace, session_id=session, explicit_task_id=task_id, input_shingles=shingles
    )


def test_single_success() -> None:
    tasks = assemble([rec(make_trace(start_s=0, status="pass"))])
    assert len(tasks) == 1
    task = tasks[0]
    assert task.attempts == 1
    assert task.succeeded is True
    assert task.first_attempt_success is True
    assert task.verification_grade == "measured"


def test_retry_then_success_groups_and_sums() -> None:
    first = make_trace(start_s=0, status="fail", cost="0.10")
    second = make_trace(start_s=60, status="pass", cost="0.15", model="model-b")
    tasks = assemble([rec(first), rec(second)])
    assert len(tasks) == 1
    task = tasks[0]
    assert task.attempts == 2
    assert task.succeeded is True
    assert task.first_attempt_success is False
    assert task.total_cost_usd == Decimal("0.25")
    assert task.total_wall_ms == 60000
    assert task.total_tokens.input == 200
    assert task.models_used == ("model-a", "model-b")


def test_all_failed() -> None:
    tasks = assemble(
        [rec(make_trace(start_s=0, status="fail")), rec(make_trace(start_s=60, status="fail"))]
    )
    assert len(tasks) == 1
    assert tasks[0].succeeded is False
    assert tasks[0].attempts == 2
    assert tasks[0].verification_grade == "measured"


def test_unknown_grade_when_no_signal() -> None:
    tasks = assemble([rec(make_trace(start_s=0, status="unknown"))])
    assert tasks[0].verification_grade == "unknown"
    assert tasks[0].succeeded is False


def test_strongest_grade_wins() -> None:
    weak = make_trace(start_s=0, status="fail", grade="derived")
    strong = make_trace(start_s=60, status="pass", grade="measured")
    tasks = assemble([rec(weak), rec(strong)])
    assert tasks[0].verification_grade == "measured"


def test_explicit_task_id_beats_heuristic() -> None:
    shared = uuid4()
    far_apart = [
        rec(make_trace(start_s=0, status="fail"), session="s-1", task_id=shared),
        rec(make_trace(start_s=9000, status="pass"), session="s-2", task_id=shared),
    ]
    tasks = assemble(far_apart)
    assert len(tasks) == 1
    assert tasks[0].task_id == shared
    assert tasks[0].attempts == 2


def test_gap_over_120s_splits() -> None:
    first = make_trace(start_s=0, duration_s=30, status="fail")
    second = make_trace(start_s=200, status="pass")  # 170s after first ended
    tasks = assemble([rec(first), rec(second)])
    assert len(tasks) == 2


def test_different_template_splits() -> None:
    first = make_trace(start_s=0, status="fail", template="template-1")
    second = make_trace(start_s=60, status="pass", template="template-2")
    tasks = assemble([rec(first), rec(second)])
    assert len(tasks) == 2


def test_different_session_splits() -> None:
    tasks = assemble(
        [
            rec(make_trace(start_s=0, status="fail"), session="s-1"),
            rec(make_trace(start_s=60, status="pass"), session="s-2"),
        ]
    )
    assert len(tasks) == 2


def test_no_session_never_merges() -> None:
    tasks = assemble(
        [
            rec(make_trace(start_s=0, status="fail"), session=None),
            rec(make_trace(start_s=60, status="pass"), session=None),
        ]
    )
    assert len(tasks) == 2


def test_low_input_overlap_splits() -> None:
    a = frozenset({"h1", "h2", "h3", "h4", "h5"})
    b = frozenset({"h1", "h6", "h7", "h8", "h9"})  # Jaccard 1/9 < 0.8
    tasks = assemble(
        [
            rec(make_trace(start_s=0, status="fail"), shingles=a),
            rec(make_trace(start_s=60, status="pass"), shingles=b),
        ]
    )
    assert len(tasks) == 2


def test_high_input_overlap_merges() -> None:
    a = frozenset({"h1", "h2", "h3", "h4", "h5"})
    b = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})  # Jaccard 5/6 > 0.8
    tasks = assemble(
        [
            rec(make_trace(start_s=0, status="fail"), shingles=a),
            rec(make_trace(start_s=60, status="pass"), shingles=b),
        ]
    )
    assert len(tasks) == 1
