"""T2 tests: full example validates, content fields are rejected, JSON round-trip is exact."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from handover.schema import SCHEMA_VERSION, Task, Trace

FP_SYS = "sha256:" + "a9" * 32
FP_IN = "sha256:" + "77" * 32
FP_SCHEMA = "sha256:" + "12" * 32
FP_ARGS = "sha256:" + "cd" * 32


def full_trace_payload() -> dict[str, Any]:
    """The SPEC.md §3.1 example, every field populated."""
    return {
        "trace_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "task_id": str(uuid4()),
        "attempt_no": 1,
        "ts_start": "2026-08-26T14:03:22.114Z",
        "ts_end": "2026-08-26T14:04:03.882Z",
        "provider": "anthropic",
        "model_id": "claude-sonnet-4-6",
        "model_version_hint": "2026-06-01",
        "endpoint_region": "us-east-1",
        "tokens": {"input": 8400, "input_cached": 6100, "output": 3100, "reasoning": 2600},
        "cost_usd": "0.0831",
        "latency": {"ttft_ms": 640, "total_ms": 41768},
        "input_shape": {
            "n_messages": 12,
            "n_chars": 31402,
            "has_attachments": False,
            "system_prompt_fingerprint": FP_SYS,
            "input_fingerprint": FP_IN,
        },
        "output_shape": {
            "type": "json",
            "n_chars": 4820,
            "json_valid": True,
            "schema_fingerprint": FP_SCHEMA,
            "has_code_block": True,
            "n_code_blocks": 2,
        },
        "tool_calls": [
            {
                "name": "run_tests",
                "args_fingerprint": FP_ARGS,
                "ts_offset_ms": 12400,
                "duration_ms": 8100,
                "status": "ok",
            }
        ],
        "verification": {
            "status": "pass",
            "method": "programmatic",
            "signal": "test_exit_code",
            "confidence": 1.0,
            "evidence_grade": "measured",
        },
        "redaction_level": "metadata_only",
        "schema_version": "1.0",
    }


def full_task_payload() -> dict[str, Any]:
    return {
        "task_id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "cluster_id": "c07",
        "attempts": 2,
        "succeeded": True,
        "first_attempt_success": False,
        "total_cost_usd": "0.1662",
        "total_wall_ms": 82190,
        "total_tokens": {"input": 16800, "output": 6200, "reasoning": 5200},
        "models_used": ["claude-sonnet-4-6"],
        "verification_grade": "measured",
    }


def test_full_trace_validates() -> None:
    trace = Trace.model_validate(full_trace_payload())
    assert trace.cost_usd == Decimal("0.0831")
    assert isinstance(trace.cost_usd, Decimal)
    assert trace.ts_start.tzinfo is not None
    assert trace.tokens.reasoning == 2600
    assert trace.schema_version == SCHEMA_VERSION


@pytest.mark.parametrize("field", ["content", "prompt", "response", "messages", "output_text"])
def test_trace_rejects_content_field_at_top_level(field: str) -> None:
    payload = full_trace_payload()
    payload[field] = "some raw content"
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


@pytest.mark.parametrize("section", ["input_shape", "output_shape", "verification"])
def test_trace_rejects_content_field_in_nested_object(section: str) -> None:
    payload = full_trace_payload()
    payload[section]["content"] = "raw text smuggled into a nested object"
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_trace_rejects_content_in_tool_call() -> None:
    payload = full_trace_payload()
    payload["tool_calls"][0]["args"] = {"query": "actual arguments"}
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_trace_rejects_naive_timestamp() -> None:
    payload = full_trace_payload()
    payload["ts_start"] = "2026-08-26T14:03:22.114"
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_trace_rejects_end_before_start() -> None:
    payload = full_trace_payload()
    payload["ts_end"] = "2026-08-26T14:00:00Z"
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_trace_rejects_float_looking_money_loss() -> None:
    trace = Trace.model_validate(full_trace_payload())
    assert trace.cost_usd == Decimal("0.0831")
    assert str(trace.cost_usd) == "0.0831"


def test_trace_rejects_truncated_fingerprint() -> None:
    payload = full_trace_payload()
    payload["input_shape"]["input_fingerprint"] = "sha256:77c2"
    with pytest.raises(ValidationError):
        Trace.model_validate(payload)


def test_trace_json_round_trip_is_exact() -> None:
    original = Trace.model_validate(full_trace_payload())
    restored = Trace.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.cost_usd == Decimal("0.0831")
    assert restored.ts_start == datetime(2026, 8, 26, 14, 3, 22, 114000, tzinfo=UTC)


def test_full_task_validates_and_round_trips() -> None:
    task = Task.model_validate(full_task_payload())
    assert task.total_cost_usd == Decimal("0.1662")
    assert task.first_attempt_success is False
    restored = Task.model_validate_json(task.model_dump_json())
    assert restored == task


def test_task_rejects_content_field() -> None:
    payload = full_task_payload()
    payload["transcript"] = "full conversation text"
    with pytest.raises(ValidationError):
        Task.model_validate(payload)


def test_task_allows_missing_cluster_before_p1() -> None:
    payload = full_task_payload()
    del payload["cluster_id"]
    assert Task.model_validate(payload).cluster_id is None


def test_task_rejects_invalid_grade() -> None:
    payload = full_task_payload()
    payload["verification_grade"] = "guessed"
    with pytest.raises(ValidationError):
        Task.model_validate(payload)
