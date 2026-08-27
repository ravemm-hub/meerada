"""T5 tests: each verifier, and the §5.1 precedence rules in the registry."""

from decimal import Decimal
from uuid import uuid4

from handover.schema.task import Task, TaskTokens
from handover.verify import Artifacts, default_registry

SCHEMA = {
    "type": "object",
    "required": ["invoice_id", "total"],
    "properties": {"invoice_id": {"type": "string"}, "total": {"type": "number"}},
}


def make_task() -> Task:
    return Task(
        task_id=uuid4(),
        tenant_id=uuid4(),
        attempts=1,
        succeeded=False,
        first_attempt_success=False,
        total_cost_usd=Decimal("0.10"),
        total_wall_ms=1000,
        total_tokens=TaskTokens(input=100, output=50, reasoning=0),
        models_used=("model-a",),
        verification_grade="unknown",
    )


def verify(artifacts: Artifacts) -> object:
    return default_registry().verify(make_task(), artifacts)


def test_exit_code_zero_passes_measured() -> None:
    verdict = default_registry().verify(make_task(), Artifacts(exit_code=0))
    assert verdict.status == "pass"
    assert verdict.evidence_grade == "measured"
    assert verdict.signal == "test_exit_code"


def test_exit_code_nonzero_fails() -> None:
    verdict = default_registry().verify(make_task(), Artifacts(exit_code=2))
    assert verdict.status == "fail"


def test_json_schema_valid_passes() -> None:
    verdict = default_registry().verify(
        make_task(),
        Artifacts(output_text='{"invoice_id": "INV-1", "total": 9.5}', json_schema=SCHEMA),
    )
    assert verdict.status == "pass"
    assert verdict.signal == "schema_validation"


def test_json_schema_invalid_or_unparseable_fails() -> None:
    registry = default_registry()
    missing = registry.verify(
        make_task(), Artifacts(output_text='{"invoice_id": "INV-1"}', json_schema=SCHEMA)
    )
    broken = registry.verify(make_task(), Artifacts(output_text="not json", json_schema=SCHEMA))
    assert missing.status == "fail"
    assert broken.status == "fail"


def test_regex_contract() -> None:
    registry = default_registry()
    good = registry.verify(
        make_task(), Artifacts(output_text="RESULT: 42", contract_regex=r"^RESULT: \d+$")
    )
    bad = registry.verify(
        make_task(), Artifacts(output_text="no result here", contract_regex=r"^RESULT: \d+$")
    )
    assert good.status == "pass"
    assert bad.status == "fail"


def test_silent_acceptance_pass_and_fail() -> None:
    registry = default_registry()
    silent = registry.verify(make_task(), Artifacts(retried_within_10m=False))
    retried = registry.verify(make_task(), Artifacts(retried_within_10m=True))
    accepted = registry.verify(make_task(), Artifacts(accepted_downstream=True))
    corrected = registry.verify(
        make_task(), Artifacts(retried_within_10m=False, correction_followed=True)
    )
    assert silent.status == "pass"
    assert silent.evidence_grade == "derived"
    assert silent.confidence == 0.7
    assert retried.status == "fail"
    assert accepted.status == "pass"
    assert accepted.confidence == 1.0
    assert corrected.status == "fail"


def test_measured_beats_derived() -> None:
    # Tests failed but the user did not retry: grade A evidence must win.
    verdict = default_registry().verify(
        make_task(), Artifacts(exit_code=1, retried_within_10m=False)
    )
    assert verdict.status == "fail"
    assert verdict.evidence_grade == "measured"

    # And the mirror: tests passed, user retried anyway — still a measured pass.
    verdict = default_registry().verify(
        make_task(), Artifacts(exit_code=0, retried_within_10m=True)
    )
    assert verdict.status == "pass"
    assert verdict.evidence_grade == "measured"


def test_within_grade_any_fail_wins() -> None:
    # Exit code passed but the output violates its schema: not a verified success.
    verdict = default_registry().verify(
        make_task(),
        Artifacts(exit_code=0, output_text="not json", json_schema=SCHEMA),
    )
    assert verdict.status == "fail"
    assert verdict.evidence_grade == "measured"


def test_no_applicable_verifier_returns_unknown() -> None:
    verdict = default_registry().verify(make_task(), Artifacts())
    assert verdict.status == "unknown"


def test_derived_only_keeps_derived_grade() -> None:
    verdict = default_registry().verify(make_task(), Artifacts(accepted_downstream=True))
    assert verdict.evidence_grade == "derived"
    assert verdict.method == "downstream"
