"""Search Lab (T2): the taxonomy, answer features, stability, intents in the report,
experiments tracking. No live calls."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from handover.visibility.experiments import Experiment, load_experiments, track
from handover.visibility.features import answer_features, jaccard
from handover.visibility.page import render_page
from handover.visibility.questions import BY_ID, INTENT_LABELS, QUESTIONS
from handover.visibility.report import build_report
from handover.visibility.run import reextract
from handover.visibility.state import Answer, State

NOW = datetime(2026, 11, 25, 7, 0, tzinfo=UTC)

CLAUDE_ITALIAN = """Based on my search, here are some excellent Italian restaurants in Tel Aviv:

**Top Recommendations:**

**Villa Mare TLV** - Highly rated (4.7-4.8 stars) with Italian and seafood cuisine, beachfront.

**Ernesto 90** - Rated 4.3 stars, reviewers note the food is as good as in Rome.

**Amore Mio** - Rated 4.3 stars, mains from 80 shekels.
"""
CLAUDE_CITES = [
    "https://www.tripadvisor.com/Restaurants-g293984-c26-Tel_Aviv.html",
    "https://secrettelaviv.com/best-italian-restaurants-tel-aviv/",
    "https://villamare.co.il/menu",
]


def test_taxonomy_covers_every_intent_and_market_and_is_interleaved() -> None:
    assert len(QUESTIONS) == len({q.id for q in QUESTIONS}) >= 130
    intents = {q.intent for q in QUESTIONS}
    assert intents == set(INTENT_LABELS)
    assert {q.country for q in QUESTIONS} >= {"IL", "US", "UK"}
    assert sum(q.lang == "he" for q in QUESTIONS) == 6
    first = [q.intent for q in QUESTIONS[:7]]
    assert len(set(first)) == 7, first  # one of each kind before any repeats
    assert BY_ID["tlv-plumber"].intent == "local" and BY_ID["us-product-headphones"].text.count(
        "$200"
    )
    assert all(q.text.strip().endswith(".") for q in QUESTIONS)


def test_features_read_candidates_ratings_prices_listicles_own_site() -> None:
    names = ["Villa Mare TLV", "Ernesto 90", "Amore Mio"]
    f = answer_features(CLAUDE_ITALIAN, CLAUDE_CITES, names)
    assert f["candidates"] == 3 and f["cites"] == 3
    assert f["rated"] == 3 and f["priced"] == 1
    assert f["listicle_cites"] == 1  # the secrettelaviv "best-italian…" path
    assert f["own_site"] == 1  # villamare.co.il
    assert (
        f["has_pick"] == 0.0 and f["has_table"] == 0.0
    )  # a "Top Recommendations" header crowns no #1 and f["distinct_hosts"] == 3


def test_jaccard_handles_empty_sets() -> None:
    assert jaccard([], []) is None
    assert jaccard(["a"], []) == 0.0
    assert jaccard(["a", "b"], ["b", "c"]) == 1 / 3


def _answer(engine: str, qid: str, when: datetime, keys: list[str], **kw: object) -> Answer:
    return Answer(
        engine=engine,
        model="m",
        query_id=qid,
        asked_at=when,
        text=kw.get("text", "t"),  # type: ignore[arg-type]
        names=[k.title() for k in keys],
        name_keys=keys,
        searches=1,
        citations=list(kw.get("citations", [])),  # type: ignore[call-overload]
        features=answer_features(str(kw.get("text", "t")), list(kw.get("citations", [])), keys),  # type: ignore[call-overload]
    )


def test_report_has_intent_blocks_and_stability() -> None:
    state = State()
    state.add(_answer("chatgpt", "tlv-plumber", NOW - timedelta(days=4), ["a", "b", "c"]))
    state.add(_answer("chatgpt", "tlv-plumber", NOW, ["a", "b", "d"]))
    state.add(_answer("chatgpt", "us-product-headphones", NOW, ["sony", "bose"]))
    state.add(_answer("claude", "tlv-plumber", NOW, []))
    report = build_report(state, QUESTIONS, ["chatgpt", "claude"], NOW)
    chat = report["engines"][0]
    assert chat["stability"] == {"value": 0.5, "n": 1}
    assert chat["choosing"]["candidates"] == {"value": 2.5, "n": 2}
    local = next(i for i in report["intents"] if i["intent"] == "local")
    assert local["engines"]["chatgpt"]["named_rate"]["n"] == 1
    assert local["engines"]["claude"]["named_rate"]["value"] == 0
    product = next(i for i in report["intents"] if i["intent"] == "product")
    assert product["engines"]["chatgpt"]["choosing"]["candidates"]["value"] == 2
    assert report["method"]["intents"][0]["intent"] == "local"
    row = next(r for r in report["queries"] if r["id"] == "us-product-headphones")
    assert row["intent"] == "product" and row["engines"]["chatgpt"]["searched"] is True


def test_experiments_track_presence_before_and_after(tmp_path: Path) -> None:
    reg = tmp_path / "experiments.json"
    reg.write_text(
        '{"experiments": [{"id": "x", "business": "Shai Plumbing Services", "aliases": ["Shai Plumbing"],'  # noqa: E501
        ' "queries": ["tlv-plumber"], "lever": "listicle", "started": "2026-11-24"}]}',
        encoding="utf-8",
    )
    exps = load_experiments(reg)
    assert exps[0].keys() == {"shai plumbing services", "shai plumbing"}
    state = State()
    state.add(_answer("chatgpt", "tlv-plumber", NOW - timedelta(days=3), ["eitan plumber"]))
    state.add(_answer("chatgpt", "tlv-plumber", NOW, ["shai plumbing services", "eitan plumber"]))
    rows = track(exps, state, ["chatgpt", "claude"])
    chat = rows[0]["engines"]["chatgpt"]
    assert chat["before"] == {"n": 1, "named": 0, "cited": 0}
    assert chat["after"] == {"n": 1, "named": 1, "cited": 0}
    assert rows[0]["engines"]["claude"]["after"]["n"] == 0
    assert load_experiments(tmp_path / "missing.json") == []
    assert Experiment(id="e", business="B", queries=[], started=date(2026, 1, 1)).lever == "none"


def test_reextract_fills_features_and_page_renders_intents() -> None:
    state = State()
    state.add(
        Answer(
            engine="claude",
            model="m",
            query_id="tlv-italian",
            asked_at=NOW,
            text=CLAUDE_ITALIAN,
            citations=CLAUDE_CITES,
            searches=1,
        )
    )
    assert reextract(state) == 1
    a = state.answers[0]
    assert a.names == ["Villa Mare TLV", "Ernesto 90", "Amore Mio"] and a.features["rated"] == 3
    html = render_page(build_report(state, QUESTIONS, ["claude"], NOW))
    assert "How each engine chooses" in html and '"intents"' in html
    assert html.count("</script>") == 4
