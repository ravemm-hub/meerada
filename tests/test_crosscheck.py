"""Cross-Check: lab detection, neutral panel seating, the report, and the
Board wiring — fakes only, no network."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from handover.copilot.crosscheck import Answer, CrossCheck, dimension_for, lab_of
from handover.copilot.serve import Board
from handover.replay.budget import DailyBudget


class _Completion:
    def __init__(self, text: str) -> None:
        self.text, self.input_tokens, self.output_tokens = text, 300, 40


class FakeModel:
    """Answers tasks with its own text; as a juror, scores by a fixed table."""

    def __init__(self, model_id: str, answer: str, scores: dict[str, float]) -> None:
        self.model_id, self.answer, self.scores = model_id, answer, scores
        self.judged: list[str] = []

    def complete(self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int):
        body = messages[-1]["content"]
        if "ANSWER:" in body and "juror" in system:
            for name, score in self.scores.items():
                if name in body:
                    self.judged.append(name)
                    return _Completion(
                        json.dumps({"score": score, "prob": 0.8, "reason": f"{model} says {score}"})
                    )
            return _Completion(json.dumps({"score": 0.5, "prob": 0.5, "reason": "unsure"}))
        return _Completion(self.answer)


def _fleet() -> dict[str, FakeModel]:
    scores = {"ANSWER-GPT": 0.9, "ANSWER-CLAUDE": 0.3, "ANSWER-GEMINI": 0.85}
    return {
        "gpt-4o-mini": FakeModel("gpt-4o-mini", "ANSWER-GPT", scores),
        "claude-haiku-4-5-20251001": FakeModel(
            "claude-haiku-4-5-20251001", "ANSWER-CLAUDE", scores
        ),
        "gemini-2.5-flash": FakeModel("gemini-2.5-flash", "ANSWER-GEMINI", scores),
        "meta/muse-spark-1.3": FakeModel("meta/muse-spark-1.3", "ANSWER-MUSE", scores),
    }


def _budget() -> DailyBudget:
    return DailyBudget(Decimal("5"), clock=lambda: datetime(2026, 9, 12, tzinfo=UTC))


def test_lab_of_and_dimension() -> None:
    assert (
        lab_of("gpt-5.6-luna") == "openai" and lab_of("anthropic/claude-fable-5.1") == "anthropic"
    )
    assert lab_of("google/gemini-3.8-flash") == "google" and lab_of("z-ai/glm-5.3-flash") == "zai"
    assert lab_of("moonshotai/kimi-k3") == "moonshot" and lab_of("llama-3.1-8b-instant") == "meta"
    assert lab_of("mystery-9000") == "unknown"
    assert dimension_for("```python\ndef f(): pass```", has_context=False) == "code_correctness"
    assert dimension_for("Sales rose.", has_context=True) == "faithfulness"
    assert dimension_for("Sales rose.", has_context=False) == "instruction_following"


def test_panel_never_seats_kin_and_one_per_lab() -> None:
    fleet = _fleet()
    cc = CrossCheck(lambda m: fleet[m], list(fleet), _budget())
    panel = cc.panel_for("gpt-4o-mini")
    assert [j.lab for j in panel] == ["anthropic", "google", "meta"]
    assert all(j.model_id != "gpt-4o-mini" for j in panel)


def test_examine_ranks_and_reports() -> None:
    fleet = _fleet()
    cc = CrossCheck(lambda m: fleet[m], list(fleet), _budget())
    answers = [
        Answer(m, m, fleet[m].answer)
        for m in ("gpt-4o-mini", "claude-haiku-4-5-20251001", "gemini-2.5-flash")
    ]
    rep = cc.examine("What happened to sales?", answers)
    rows = rep.as_dict()["rows"]
    assert [r["model"] for r in rows][:2] == ["gpt-4o-mini", "gemini-2.5-flash"]
    assert (
        rows[0]["status"] == "pass" and rows[-1]["status"] == "fail" and rows[0]["agreement"] == 1.0
    )
    assert "WINNER: gpt-4o-mini" in rep.text and "other labs" in rep.text
    assert rep.cost_usd > 0
    # no juror ever examined its own family's answer
    assert "ANSWER-GPT" not in fleet["gpt-4o-mini"].judged
    assert "ANSWER-CLAUDE" not in fleet["claude-haiku-4-5-20251001"].judged


def test_thin_panel_uses_what_we_have_and_says_so() -> None:
    fleet = {k: v for k, v in _fleet().items() if k in ("gpt-4o-mini", "claude-haiku-4-5-20251001")}
    cc = CrossCheck(lambda m: fleet[m], list(fleet), _budget())
    rep = cc.examine("q", [Answer("s1", "gpt-4o-mini", "ANSWER-GPT")])
    row = rep.as_dict()["rows"][0]
    # one juror (claude) examined gpt's answer: a score, labelled as a thin panel, never grade C
    assert row["n_judges"] == 1 and row["score"] == 0.9 and row["status"] == "pass"
    assert row["evidence"] == "declared" and "thin panel" in row["note"]
    assert "examined by 1 model ·" in rep.text and "WINNER: gpt-4o-mini" in rep.text
    assert "(thin panel)" in rep.text


def test_no_other_lab_is_reported_not_faked() -> None:
    fleet = {k: v for k, v in _fleet().items() if k == "gpt-4o-mini"}
    cc = CrossCheck(lambda m: fleet[m], list(fleet), _budget())
    rep = cc.examine("q", [Answer("s1", "gpt-4o-mini", "ANSWER-GPT")])
    row = rep.as_dict()["rows"][0]
    assert row["status"] == "unknown" and "second lab" in row["note"] and "NO WINNER" in rep.text


def test_board_crosscheck_lands_on_the_ledger() -> None:
    fleet = _fleet()
    board = Board(lambda m: fleet[m])
    for sid, m in (
        ("s1", "gpt-4o-mini"),
        ("s2", "claude-haiku-4-5-20251001"),
        ("s3", "gemini-2.5-flash"),
    ):
        board.send(sid, m, "What happened to sales?")
    out = board.crosscheck(["s1", "s2", "s3"], "xc1", list(fleet))
    assert (
        out["error"] == ""
        and out["title"] == "🔎 Cross-check"
        and out["report"]["rows"][0]["model"] == "gpt-4o-mini"
    )
    assert out["total_cost"] > 0 and board.sessions["xc1"].history[-1].role == "assistant"
    assert board.crosscheck(["nope"], "xc2", list(fleet))["error"]
