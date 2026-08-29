"""The migration quality guarantee: candidate must be AS GOOD AS the incumbent,
not merely well-formed. This is the verifier that makes 'no quality loss' real."""

from decimal import Decimal
from uuid import uuid4

from handover.schema.task import Task, TaskTokens
from handover.verify import Artifacts, default_registry


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
        models_used=("candidate",),
        verification_grade="unknown",
    )


def verdict(expected: str, candidate: str, exit_code: int | None = None):
    return default_registry().verify(
        make_task(),
        Artifacts(output_text=candidate, expected_output=expected, candidate_exit_code=exit_code),
    )


def test_json_same_values_passes() -> None:
    v = verdict('{"name": "Acme", "amount": 1240.5}', '{"amount": 1240.5, "name": "Acme"}')
    assert v.status == "pass"
    assert v.signal == "equiv_json_fields"
    assert v.evidence_grade == "measured"


def test_json_changed_value_is_a_regression() -> None:
    # The classic silent regression: valid JSON, right shape, WRONG value.
    v = verdict('{"name": "Acme", "amount": 1240.5}', '{"name": "Acme", "amount": 9999.0}')
    assert v.status == "fail"


def test_json_missing_incumbent_key_fails() -> None:
    v = verdict('{"name": "Acme", "amount": 1240.5}', '{"name": "Acme"}')
    assert v.status == "fail"


def test_json_extra_candidate_key_is_tolerated() -> None:
    v = verdict('{"name": "Acme"}', '{"name": "Acme", "note": "added detail"}')
    assert v.status == "pass"


def test_candidate_not_json_when_expected_is_fails() -> None:
    v = verdict('{"name": "Acme"}', "Acme, amount 1240.5")
    assert v.status == "fail"
    assert v.signal == "equiv_json_unparseable"


def test_number_drift_in_text_is_caught() -> None:
    # Same words, different number — the extraction silently changed the amount.
    v = verdict("The total is 1240.50 dollars.", "The total is 9999.00 dollars.")
    assert v.status == "fail"
    assert v.signal == "equiv_number_mismatch"


def test_text_exact_after_normalization_passes() -> None:
    v = verdict("The  answer   is Yes.", "the answer is yes.")
    assert v.status == "pass"
    assert v.signal == "equiv_text_exact"


def test_text_meaning_change_fails() -> None:
    v = verdict("The contract is approved.", "The contract is rejected.")
    assert v.status == "fail"


def test_code_uses_same_tests_not_text_diff() -> None:
    # Different code text, but it passed the SAME tests -> equivalent quality.
    passed = verdict("def f(): return 1", "def f():\n    return 1  # refactored", exit_code=0)
    assert passed.status == "pass"
    assert passed.signal == "equiv_test_pass"
    failed = verdict("def f(): return 1", "def f(): return 2", exit_code=1)
    assert failed.status == "fail"


def test_equivalence_beats_schema_only_grade() -> None:
    # Both schema-valid, but the candidate changed a value: equivalence must FAIL
    # even though a schema check alone would pass. Quality > format.
    schema = {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "number"}},
    }
    v = default_registry().verify(
        make_task(),
        Artifacts(
            output_text='{"amount": 9999.0}',
            expected_output='{"amount": 1240.5}',
            json_schema=schema,
        ),
    )
    assert v.status == "fail"  # schema-valid but not equivalent -> regression caught
    assert v.evidence_grade == "measured"
