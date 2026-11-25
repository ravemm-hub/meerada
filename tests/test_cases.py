"""T3: the ChatGPT fan-out variant, repeated runs, named vs cited, the test-case page."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from handover.replay.budget import DailyBudget
from handover.visibility import engines as eng
from handover.visibility.cases import render_cases
from handover.visibility.experiments import Experiment, cited_in, named_in, track
from handover.visibility.questions import QUESTIONS
from handover.visibility.report import build_report
from handover.visibility.run import tick
from handover.visibility.state import Answer, State

NOW = datetime(2026, 11, 26, 7, 0, tzinfo=UTC)


def test_fanout_variant_uses_gpt5_mini_with_reasoning() -> None:
    calls: list[dict[str, Any]] = []

    def post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        calls.append(body)
        return {"output": [], "usage": {}}

    built, skipped = eng.engines_from_env(["chatgpt", "chatgpt5"], {"OPENAI_API_KEY": "k"}, post)
    assert [e.name for e in built] == ["chatgpt", "chatgpt5"] and not skipped
    assert built[1].model == "gpt-5-mini" and built[1].estimate_usd == Decimal("0.040")
    built[0].ask("q")
    built[1].ask("q")
    assert "reasoning" not in calls[0] and calls[1]["reasoning"] == {"effort": "low"}
    assert "chatgpt5" in eng.ALL_ENGINES


class _Stub:
    name = "chatgpt"
    model = "stub"
    estimate_usd = Decimal("0.01")

    def __init__(self) -> None:
        self.calls = 0

    def ask(self, question: str) -> eng.Reply:
        self.calls += 1
        return eng.Reply(
            "- **Alpha Plumbing**\n- **Beta Pipes**", ["https://alpha-plumbing.co.il/x"]
        )


def test_tick_repeats_each_question_runs_times(tmp_path: Path) -> None:
    stub = _Stub()
    state = State()
    added = tick(
        state,
        [stub],
        DailyBudget(Decimal("1")),
        per_tick=2,
        now=NOW,
        queries=QUESTIONS[:2],
        save=tmp_path / "s.json",
        runs=3,
    )
    assert stub.calls == 6 and len(added) == 6
    assert {a.query_id for a in added} == {QUESTIONS[0].id, QUESTIONS[1].id}


def test_named_vs_cited_and_tracking_with_controls() -> None:
    assert cited_in("alpha-plumbing.co.il", ["https://www.alpha-plumbing.co.il/about"])
    assert cited_in("https://alpha-plumbing.co.il/", ["https://shop.alpha-plumbing.co.il"])
    assert not cited_in("alpha-plumbing.co.il", ["https://notalpha-plumbing.co.il"])
    assert not cited_in("", ["https://x.com"])
    assert named_in({"alpha plumbing"}, ["alpha plumbing services"])

    exp = Experiment(
        id="alpha",
        business="Alpha Plumbing",
        domain="alpha-plumbing.co.il",
        queries=["tlv-plumber"],
        lever="guide",
        started=date(2026, 11, 25),
    )
    ctrl = Experiment(
        id="gamma",
        business="Gamma Drains",
        queries=["tlv-plumber"],
        started=date(2026, 11, 25),
        control=True,
    )
    state = State()
    before = NOW - timedelta(days=3)
    state.add(
        Answer(
            engine="chatgpt",
            model="m",
            query_id="tlv-plumber",
            asked_at=before,
            text="t",
            names=["Beta Pipes"],
            name_keys=["beta pipes"],
            citations=["https://alpha-plumbing.co.il/"],
        )
    )
    state.add(
        Answer(
            engine="chatgpt",
            model="m",
            query_id="tlv-plumber",
            asked_at=NOW,
            text="t",
            names=["Alpha Plumbing", "Beta Pipes"],
            name_keys=["alpha plumbing", "beta pipes"],
        )
    )
    rows = track([exp, ctrl], state, ["chatgpt", "claude"])
    chat = rows[0]["engines"]["chatgpt"]
    assert chat["before"] == {"n": 1, "named": 0, "cited": 1}
    assert chat["after"] == {"n": 1, "named": 1, "cited": 0}
    assert chat["series"][-1]["names"] == ["Alpha Plumbing", "Beta Pipes"]
    assert rows[1]["control"] is True and rows[1]["engines"]["chatgpt"]["after"]["named"] == 0
    assert rows[0]["engines"]["claude"]["before"]["n"] == 0

    report = build_report(state, QUESTIONS, ["chatgpt", "claude"], NOW, [exp, ctrl])
    html = render_cases(report)
    assert "Alpha Plumbing" in html and "control" in html and html.count("</script>") == 4
    empty = render_cases(build_report(State(), QUESTIONS, ["chatgpt"], NOW, []))
    assert "No test cases published yet" in empty
