"""Meerada Search MVP: consensus ranking, static query pages, the live API service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from handover.visibility import api as api_mod
from handover.visibility.consensus import rank
from handover.visibility.engines import Reply
from handover.visibility.pages import build_query_pages
from handover.visibility.state import Answer, State

NOW = datetime(2026, 11, 26, 8, 0, tzinfo=UTC)


def _a(engine: str, names: list[str], qid: str = "tlv-plumber", **kw: object) -> Answer:
    return Answer(
        engine=engine,
        model="m",
        query_id=qid,
        asked_at=NOW,
        text="t",
        names=names,
        name_keys=[n.lower() for n in names],
        searches=1,
        citations=list(kw.get("citations", ["https://maps.google.com/x"])),
    )  # type: ignore[call-overload]


def test_rank_weights_share_and_position() -> None:
    answers = [
        _a("chatgpt", ["Alpha", "Beta"]),
        _a("chatgpt", ["Alpha"]),
        _a("claude", ["Beta", "Alpha"]),
        _a(
            "claude",
            [],
        ),
        Answer(
            engine="claude", model="m", query_id="tlv-plumber", asked_at=NOW, text="", error="x"
        ),
    ]
    r = rank(answers)
    assert r["runs"] == 4 and r["engines"] == {"chatgpt": 2, "claude": 2}
    names = [x["name"] for x in r["results"]]
    assert names == ["Alpha", "Beta"]
    alpha = r["results"][0]
    assert alpha["engines"]["chatgpt"] == {"named": 2, "runs": 2, "best_position": 1}
    assert alpha["engines"]["claude"]["named"] == 1 and alpha["best_position"] == 1
    assert alpha["sources"] == ["Google"]
    # chatgpt: 0.40*1*1 ; claude: 0.15*0.5*(1/sqrt2)
    assert abs(alpha["score"] - (0.40 + 0.15 * 0.5 * (1 / 2**0.5))) < 1e-3
    assert rank([])["results"] == [] and rank([])["last_asked"] is None


def test_build_query_pages_writes_json_html_and_index(tmp_path: Path) -> None:
    state = State()
    state.add(_a("chatgpt", ["Alpha Plumbing", "Beta Pipes"]))
    state.add(_a("chatgpt", ["Sony WH-CH720N"], qid="us-product-headphones"))
    written = build_query_pages(state, tmp_path / "s")
    names = sorted(p.name for p in written)
    assert "tlv-plumber.html" in names and "tlv-plumber.json" in names and "index.json" in names
    html = (tmp_path / "s" / "tlv-plumber.html").read_text(encoding="utf-8")
    assert (
        "Alpha Plumbing" in html
        and "Is your business here?" in html
        and '"@type": "ItemList"' in html
    )
    index = (tmp_path / "s" / "index.json").read_text(encoding="utf-8")
    assert '"us-product-headphones"' in index and "Sony WH-CH720N" in index


class _Stub:
    name = "chatgpt"
    model = "stub"
    estimate_usd = Decimal("0.03")

    def ask(self, question: str) -> Reply:
        return Reply(
            "1. **Gamma Clinic** — good\n2. **Delta Dental** — fine", ["https://yelp.com/x"]
        )


def test_service_answers_lab_questions_from_state_and_live_otherwise() -> None:
    svc = api_mod.SearchService.__new__(api_mod.SearchService)
    import threading

    svc._lock = threading.Lock()
    svc._state = State()
    svc._state.add(_a("chatgpt", ["Alpha Plumbing"]))
    svc._state_at = 10**12  # never refresh
    svc._cache = {}
    svc._ip_live = {}
    svc.budget = api_mod.DailyBudget(Decimal("0.05"))
    svc.engines = [_Stub()]
    svc.skipped = {}
    lab = svc.search(
        "I'm looking for a plumber in Tel Aviv for a leaking pipe this week. Who do you recommend? Please name specific ones.",  # noqa: E501
        "1.1.1.1",
    )
    assert (
        lab["source"] == "lab"
        and lab["matched"] == "tlv-plumber"
        and lab["results"][0]["name"] == "Alpha Plumbing"
    )
    short = svc.search("a yoga studio in London for a beginner", "9.9.9.9")
    assert short["source"] == "lab" and short["matched"] == "ldn-yoga"
    live = svc.search("a good dentist in Haifa", "1.1.1.1")
    assert live["source"] == "live" and [r["name"] for r in live["results"]] == [
        "Gamma Clinic",
        "Delta Dental",
    ]
    cached = svc.search("A good  dentist in Haifa ", "2.2.2.2")
    assert cached["source"] == "cache"
    assert svc.budget.spent_today() == Decimal("0.03")
    over = svc.search("another new question", "1.1.1.1")
    assert over["source"] == "unavailable" and "budget" in over["reason"]
    svc.budget = api_mod.DailyBudget(Decimal("9"))
    svc._ip_live["3.3.3.3"] = (datetime.now(tz=UTC).strftime("%Y-%m-%d"), api_mod.FREE_LIVE_PER_IP)
    limited = svc.search("yet another question", "3.3.3.3")
    assert limited["source"] == "unavailable" and "free live" in limited["reason"]
