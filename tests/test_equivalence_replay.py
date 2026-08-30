"""Piece 2: the replay now measures 'as good as the incumbent' — a cheaper
model that changes values FAILS the gap report, not merely passes on format."""

from decimal import Decimal
from uuid import uuid4

from handover.replay.budget import DailyBudget
from handover.replay.equivalence_verifier import (
    equivalence_case_verifier,
    schema_case_verifier,
)
from handover.replay.runner import ReplayCase, ReplayResult, replay


def case(case_id: str, expected_ref: str) -> ReplayCase:
    return ReplayCase(
        case_id=uuid4(),
        cluster_id="c01",
        input_ref=f"trace://{case_id}/input",
        expected_ref=expected_ref,
        verifier_spec="output_equivalence",
        input_fingerprint="sha256:" + case_id.rjust(64, "0"),
        cache_key="sha256:" + "a" * 64,
    )


class StoreClient:
    """Fake in-tenant client: candidate outputs come from a fixed map."""

    model_id = "candidate"
    supports_batch = False

    def __init__(self, outputs: dict[str, str]) -> None:
        self._outputs = outputs

    def run(self, c: ReplayCase) -> ReplayResult:
        return ReplayResult(
            output_ref=f"cand://{c.input_fingerprint}", cost_usd=Decimal("0.01"), latency_ms=100
        )

    def run_batch(self, cases: list[ReplayCase]) -> list[ReplayResult]:
        return [self.run(c) for c in cases]


def test_candidate_matching_incumbent_passes() -> None:
    expected = {"trace://x/output": '{"amount": 1240.5}'}
    candidate = {"cand://sha256:" + "x".rjust(64, "0"): '{"amount": 1240.5, "note": "extra ok"}'}
    verifier = equivalence_case_verifier(expected.get, candidate.get)
    report = replay(
        [case("x", "trace://x/output")],
        StoreClient(candidate),
        verifier,
        DailyBudget(Decimal("1")),
    )
    assert report.outcomes[0].passed is True


def test_candidate_changing_a_value_fails_the_gap() -> None:
    expected = {"trace://x/output": '{"amount": 1240.5}'}
    candidate = {"cand://sha256:" + "x".rjust(64, "0"): '{"amount": 9999.0}'}  # wrong value
    verifier = equivalence_case_verifier(expected.get, candidate.get)
    report = replay(
        [case("x", "trace://x/output")],
        StoreClient(candidate),
        verifier,
        DailyBudget(Decimal("1")),
    )
    assert report.outcomes[0].passed is False  # quality regression caught


def test_unresolvable_output_never_passes() -> None:
    verifier = equivalence_case_verifier(lambda ref: None, lambda ref: None)
    report = replay(
        [case("x", "trace://x/output")], StoreClient({}), verifier, DailyBudget(Decimal("1"))
    )
    assert report.outcomes[0].passed is False


def test_code_case_uses_exit_code() -> None:
    expected = {"trace://x/output": "def f(): return 1"}
    candidate = {"cand://sha256:" + "x".rjust(64, "0"): "def f():\n    return 1  # refactor"}
    verifier = equivalence_case_verifier(expected.get, candidate.get, exit_code_of=lambda c, r: 0)
    report = replay(
        [case("x", "trace://x/output")],
        StoreClient(candidate),
        verifier,
        DailyBudget(Decimal("1")),
    )
    assert report.outcomes[0].passed is True


def test_schema_fallback_when_no_golden_output() -> None:
    schema = {
        "type": "object",
        "required": ["amount"],
        "properties": {"amount": {"type": "number"}},
    }
    candidate = {"cand://sha256:" + "x".rjust(64, "0"): '{"amount": 5}'}
    verifier = schema_case_verifier(candidate.get, lambda c: schema)
    report = replay(
        [case("x", "trace://x/output")],
        StoreClient(candidate),
        verifier,
        DailyBudget(Decimal("1")),
    )
    assert report.outcomes[0].passed is True
