"""The jury (SPEC §5.2): three labs, no kin, reversed pairwise runs, Fleiss'
kappa, low agreement -> unknown, hard budget, verdicts stored — fakes only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from handover.replay.budget import DailyBudget
from handover.schema.verdict import JudgeRequest, category
from handover.verify.jury import Juror, Jury, JuryConfigError, fleiss_kappa
from handover.verify.jury_store import JuryStore
from handover.verify.rubrics import parse_verdict, system_prompt, user_prompt


class _Completion:
    def __init__(self, text: str) -> None:
        self.text, self.input_tokens, self.output_tokens = text, 400, 60


class FakeJudge:
    """Answers with a fixed score; records what it was shown."""

    def __init__(self, score: float, prob: float = 0.9) -> None:
        self.score, self.prob = score, prob
        self.seen: list[str] = []

    def complete(self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int):
        self.seen.append(messages[-1]["content"])
        return _Completion(
            json.dumps(
                {
                    "score": self.score,
                    "prob": self.prob,
                    "spans": [{"start": 0, "end": 4, "reason": "made up"}],
                    "reason": "unsupported claim",
                }
            )
        )


def _budget(cap: str = "1.00") -> DailyBudget:
    return DailyBudget(Decimal(cap), clock=lambda: datetime(2026, 9, 12, tzinfo=UTC))


def _jury(
    scores: tuple[float, float, float] = (0.9, 0.85, 0.8), **kw
) -> tuple[Jury, list[FakeJudge]]:
    fakes = [FakeJudge(s) for s in scores]
    jurors = [
        Juror("gpt-4o-mini", "openai", fakes[0]),
        Juror("claude-haiku-4-5-20251001", "anthropic", fakes[1]),
        Juror("gemini-2.5-flash", "google", fakes[2]),
    ]
    return Jury(jurors, kw.pop("budget", _budget()), **kw), fakes


REQ = JudgeRequest(
    action="judge",
    dimension="faithfulness",
    prompt="Summarize the memo.",
    answer="Sales rose 12%.",
    context="Sales rose 12% in Q2.",
    answer_family="meta",
)


def test_three_labs_required() -> None:
    f = FakeJudge(0.9)
    with pytest.raises(JuryConfigError):
        Jury([Juror("a", "openai", f), Juror("b", "openai", f), Juror("c", "google", f)], _budget())
    with pytest.raises(JuryConfigError):
        Jury([Juror("a", "openai", f), Juror("b", "google", f)], _budget())  # default needs 3


def test_thin_panel_scores_but_is_only_declared_evidence() -> None:
    f = FakeJudge(0.9)
    jury = Jury([Juror("a", "openai", f), Juror("b", "google", f)], _budget(), min_jurors=2)
    res = jury.judge(REQ)
    assert res.n_judges == 2 and not res.low_agreement and res.verification.status == "pass"
    assert res.verification.evidence_grade == "declared"  # grade C needs three labs
    assert res.verification.confidence < 0.9 * 1.0  # discounted by 2/3
    with pytest.raises(JuryConfigError):
        Jury([Juror("a", "openai", f), Juror("b", "openai", f)], _budget(), min_jurors=2)


def test_unanimous_pass_is_derived_evidence_with_spans_and_cost() -> None:
    jury, fakes = _jury()
    res = jury.judge(REQ)
    assert res.n_judges == 3 and not res.low_agreement and res.verification.status == "pass"
    assert res.verification.evidence_grade == "derived" and res.verification.method == "judge"
    assert res.verification.signal == "jury_faithfulness"
    assert res.score == pytest.approx(0.85) and len(res.flagged_spans) == 3
    assert res.cost_usd > 0 and all("CONTEXT" in s for f in fakes for s in f.seen)


def test_kin_never_judges_and_a_short_panel_is_unknown() -> None:
    jury, fakes = _jury()
    res = jury.judge(REQ.model_copy(update={"answer_family": "anthropic"}))
    assert [v.judge_lab for v in res.verdicts] == ["openai", "google"]
    assert fakes[1].seen == [] and res.n_judges == 2
    assert res.low_agreement and res.verification.status == "unknown"


def test_split_panel_is_low_agreement() -> None:
    jury, _ = _jury((0.9, 0.5, 0.1))
    res = jury.judge(REQ)
    assert res.agreement == pytest.approx(1 / 3, abs=1e-3) and res.low_agreement
    assert res.verification.status == "unknown" and res.verification.evidence_grade == "declared"


def test_compare_runs_both_orders_and_neutralises_position() -> None:
    jury, fakes = _jury((0.8, 0.8, 0.8))
    req = REQ.model_copy(
        update={"action": "compare", "dimension": "pairwise_preference", "answer_b": "Sales fell."}
    )
    res = jury.judge(req)
    assert len(res.verdicts) == 6 and {v.position for v in res.verdicts} == {"ab", "ba"}
    # a juror that always says "A is better" regardless of order nets out to a tie
    assert res.score == pytest.approx(0.5)
    first, second = fakes[0].seen
    assert "ANSWER A:\nSales rose 12%." in first and "ANSWER B:\nSales fell." in first
    assert "ANSWER A:\nSales fell." in second and "ANSWER B:\nSales rose 12%." in second


def test_budget_stops_the_panel_hard() -> None:
    jury, fakes = _jury(budget=_budget("0.00"))
    res = jury.judge(REQ)
    assert res.budget_stopped and res.n_judges == 0 and res.verification.status == "unknown"
    assert all(f.seen == [] for f in fakes)


def test_fleiss_kappa_known_values() -> None:
    assert fleiss_kappa([[3, 0, 0], [0, 3, 0], [0, 0, 3], [3, 0, 0]]) == pytest.approx(1.0)
    assert fleiss_kappa([[1, 1, 1], [1, 1, 1]]) == pytest.approx(-0.5)
    assert fleiss_kappa([[3, 0, 0]]) is None and fleiss_kappa([[2, 1, 0], [3, 0, 0, 0]]) is None
    assert category(0.1) == 0 and category(0.5) == 1 and category(0.9) == 2


def test_judge_many_stamps_batch_kappa() -> None:
    jury, _ = _jury((0.9, 0.9, 0.9))
    reqs = [REQ, REQ.model_copy(update={"answer": "Sales rose 12% in Q2."})]
    out = jury.judge_many(reqs)
    assert [r.kappa for r in out] == [pytest.approx(1.0)] * 2 and not any(
        r.low_agreement for r in out
    )


def test_rubric_contract_and_parser() -> None:
    assert "padding" in system_prompt("faithfulness") and "JSON" in system_prompt(
        "code_correctness"
    )
    assert "ANSWER A" in user_prompt(REQ.model_copy(update={"action": "compare", "answer_b": "x"}))
    score, prob, spans, reason = parse_verdict(
        'junk {"score": 1.7, "prob": "0.3", "spans": [{"start": 2, "end": 99}]}', 10
    )
    assert score == 1.0 and prob == 0.3 and spans[0].end == 10 and reason == ""
    assert parse_verdict("no json here", 5)[:2] == (0.5, 0.0)


def test_store_keeps_content_in_tenant_and_exports_metadata_only(tmp_path: Path) -> None:
    store = JuryStore(tmp_path / "jury.sqlite")
    jury, _ = _jury(store=store.save)
    jury.judge(REQ)
    jury.judge(REQ.model_copy(update={"answer": "Sales fell 50%."}))
    assert store.count() == 2
    rows = store.training_rows()
    assert (
        len(rows) == 2 and rows[0]["request"]["answer"] == "Sales rose 12%." and rows[0]["reasons"]
    )
    meta = store.export_metadata()
    dumped = json.dumps(meta)
    assert "Sales" not in dumped and "memo" not in dumped and "unsupported claim" not in dumped
    assert meta[0]["n_judges"] == 3 and meta[0]["status"] == "pass" and len(meta[0]["judges"]) == 3
    assert (
        meta[0]["prompt_hash"] == meta[1]["prompt_hash"]
        and meta[0]["answer_hash"] != meta[1]["answer_hash"]
    )
    store.close()
