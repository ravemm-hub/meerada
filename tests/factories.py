"""Shared builders for tests. Not a test module."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from handover.metrics.waste import TaskTraces
from handover.schema.task import Task, TaskTokens
from handover.schema.trace import (
    InputShape,
    Latency,
    OutputShape,
    Tokens,
    ToolCall,
    Trace,
    Verification,
)

T0 = datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC)


def fp(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


def make_trace(
    *,
    start_s: int = 0,
    duration_s: int = 30,
    status: Literal["pass", "fail", "unknown"] = "pass",
    template: str = "template-1",
    model: str = "model-a",
    cost: str = "0.10",
    input_tokens: int = 0,
    cached_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
    tools: tuple[str, ...] = (),
    output_type: Literal["json", "text", "code", "mixed"] = "text",
    schema_seed: str | None = None,
    n_chars: int = 50,
) -> Trace:
    start = T0 + timedelta(seconds=start_s)
    return Trace(
        trace_id=uuid4(),
        tenant_id=uuid4(),
        task_id=uuid4(),
        attempt_no=1,
        ts_start=start,
        ts_end=start + timedelta(seconds=duration_s),
        provider="anthropic",
        model_id=model,
        model_version_hint="unknown",
        endpoint_region="unknown",
        tokens=Tokens(
            input=input_tokens,
            input_cached=cached_tokens,
            output=output_tokens,
            reasoning=reasoning_tokens,
        ),
        cost_usd=Decimal(cost),
        latency=Latency(ttft_ms=100, total_ms=duration_s * 1000),
        input_shape=InputShape(
            n_messages=2,
            n_chars=100,
            has_attachments=False,
            system_prompt_fingerprint=fp(template),
            input_fingerprint=fp(f"input-{start_s}"),
        ),
        output_shape=OutputShape(
            type=output_type,
            n_chars=n_chars,
            json_valid=output_type == "json",
            schema_fingerprint=fp(schema_seed) if schema_seed else None,
            has_code_block=output_type in ("code", "mixed"),
            n_code_blocks=1 if output_type in ("code", "mixed") else 0,
        ),
        tool_calls=tuple(
            ToolCall(
                name=name,
                args_fingerprint=fp(f"args-{name}"),
                ts_offset_ms=i * 1000,
                duration_ms=500,
                status="ok",
            )
            for i, name in enumerate(tools)
        ),
        verification=Verification(
            status=status,
            method="programmatic",
            signal="test_exit_code" if status != "unknown" else "none",
            confidence=1.0 if status != "unknown" else 0.0,
            evidence_grade="measured" if status != "unknown" else "declared",
        ),
    )


def make_task(
    *,
    attempts: int = 1,
    succeeded: bool = True,
    cost: Decimal | str = "0.10",
    wall_ms: int = 30000,
    grade: Literal["measured", "derived", "declared", "unknown"] = "measured",
    model: str = "model-a",
) -> Task:
    return Task(
        task_id=uuid4(),
        tenant_id=uuid4(),
        attempts=attempts,
        succeeded=succeeded,
        first_attempt_success=succeeded and attempts == 1,
        total_cost_usd=Decimal(cost),
        total_wall_ms=wall_ms,
        total_tokens=TaskTokens(input=0, output=0, reasoning=0),
        models_used=(model,),
        verification_grade=grade,
    )


def task_of(
    *traces: Trace,
    grade: Literal["measured", "derived", "declared", "unknown"] | None = None,
) -> TaskTraces:
    """Build a Task consistent with its traces and pair them for waste analysis."""
    succeeded = any(t.verification.status == "pass" for t in traces)
    if grade is None:
        verified = [t for t in traces if t.verification.status != "unknown"]
        grade = verified[0].verification.evidence_grade if verified else "unknown"
    task = Task(
        task_id=uuid4(),
        tenant_id=traces[0].tenant_id,
        attempts=len(traces),
        succeeded=succeeded,
        first_attempt_success=traces[0].verification.status == "pass",
        total_cost_usd=sum((t.cost_usd for t in traces), Decimal("0")),
        total_wall_ms=sum(t.latency.total_ms for t in traces),
        total_tokens=TaskTokens(
            input=sum(t.tokens.input for t in traces),
            output=sum(t.tokens.output for t in traces),
            reasoning=sum(t.tokens.reasoning for t in traces),
        ),
        models_used=tuple(dict.fromkeys(t.model_id for t in traces)),
        verification_grade=grade,
    )
    return TaskTraces(task=task, traces=tuple(traces))
