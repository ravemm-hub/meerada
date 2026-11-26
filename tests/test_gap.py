"""Gap pages (public lead pages) and the outreach drafts, on fixtures only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from handover.visibility.gap import build_gap_pages, cited_hosts, slug_for
from handover.visibility.google import GoogleResult, GoogleSnapshot
from handover.visibility.outreach import build_outreach, named_counts
from handover.visibility.questions import BY_ID
from handover.visibility.state import Answer, State

Q = BY_ID["tlv-electrician"]


def _answer(engine: str, names: list[str], cites: list[str]) -> Answer:
    return Answer(
        engine=engine,
        model="m",
        query_id=Q.id,
        asked_at=datetime(2026, 11, 26, tzinfo=UTC),
        text="- " + "\n- ".join(names),
        citations=cites,
        names=names,
        name_keys=[n.lower() for n in names],
    )


def _state() -> State:
    return State(
        answers=[
            _answer(
                "chatgpt",
                ["Asher Electric", "Amnon Electric"],
                ["https://www.google.com/maps/search/x"],
            ),
            _answer(
                "chatgpt", ["Asher Electric"], ["https://easy.co.il/x", "https://google.com/y"]
            ),
            _answer("claude", [], []),
        ]
    )


def _snapshot(tmp_path: Path) -> Path:
    snap = GoogleSnapshot(
        query_id=Q.id,
        query="electrician Tel Aviv",
        locale="en-IL",
        read_at="2026-11-26",
        results=[
            GoogleResult(rank=1, name="חשמלאי חירום 24 שעות", rating=4.9, reviews=167),
            GoogleResult(rank=2, name="אמנון חשמל", rating=4.8, reviews=21),
            GoogleResult(rank=3, name="Jacob electrician Tel Aviv 24 hours", rating=5.0, reviews=1),
        ],
    )
    d = tmp_path / "google"
    d.mkdir()
    (d / f"{Q.id}.json").write_text(
        json.dumps(snap.model_dump(), ensure_ascii=False), encoding="utf-8"
    )
    return d


def test_slug_and_hosts() -> None:
    assert (
        slug_for("Jacob electrician Tel Aviv 24 hours", "tlv-electrician", "k")
        == "jacob-electrician-tel-aviv-24-hours-tlv-electrician"
    )
    assert slug_for("אמנון חשמל", "tlv-electrician", "אמנון חשמל").startswith("tlv-electrician-")
    assert cited_hosts(_state().answers) == [("google.com", 2), ("easy.co.il", 1)]


def test_gap_pages_state_the_count_and_the_bar(tmp_path: Path) -> None:
    out = tmp_path / "gap"
    written = build_gap_pages(_state(), out, (Q,), _snapshot(tmp_path))
    leads = json.loads((out / "leads.json").read_text(encoding="utf-8"))["leads"]
    assert len(written) == 5 and len(leads) == 3
    by_name = {r["business"]: r for r in leads}
    assert by_name["אמנון חשמל"]["named_runs"] == 1 and by_name["אמנון חשמל"]["ai_rank"] == 2
    assert (
        by_name["חשמלאי חירום 24 שעות"]["named_runs"] == 0
        and by_name["חשמלאי חירום 24 שעות"]["quality"] is True
    )
    assert leads[0]["business"] == "חשמלאי חירום 24 שעות"  # invisible + above the bar first
    jacob = (out / f"{by_name['Jacob electrician Tel Aviv 24 hours']['slug']}.html").read_text(
        encoding="utf-8"
    )
    assert "Named in 0 of 3 AI answers" in jacob and "Below the quality bar" in jacob
    assert (
        "google.com x2" in jacob and "Start a free pilot" in jacob and "hello@meerada.app" in jacob
    )
    amnon = (out / f"{by_name['אמנון חשמל']['slug']}.html").read_text(encoding="utf-8")
    assert "Named in 1 of 3 AI answers" in amnon and 'dir="rtl"' in amnon and "★" not in amnon


def test_outreach_drafts_use_measured_numbers(tmp_path: Path) -> None:
    exps = {
        "experiments": [
            {
                "id": "tlv-electrician-amnon",
                "business": "אמנון חשמל",
                "aliases": ["Amnon Electric"],
                "domain": "amnon.example",
                "queries": [Q.id],
                "lever": "guide",
                "started": "2026-11-26",
            },
            {
                "id": "tlv-electrician-ctrl",
                "business": "Control Co",
                "queries": [Q.id],
                "lever": "none",
                "control": True,
            },
        ]
    }
    p = tmp_path / "experiments.json"
    p.write_text(json.dumps(exps, ensure_ascii=False), encoding="utf-8")
    st = _state()
    assert named_counts(st, Q.id, ["אמנון חשמל", "Amnon Electric"]) == {
        "chatgpt": (1, 2),
        "claude": (0, 1),
    }
    out = tmp_path / "gap"
    build_gap_pages(st, out, (Q,), _snapshot(tmp_path))
    written = build_outreach(p, st, tmp_path / "outreach", out / "leads.json")
    assert [w.name for w in written] == ["tlv-electrician-amnon.md"]
    text = written[0].read_text(encoding="utf-8")
    assert "named 1 times (chatgpt 1/2, claude 0/1)" in text and "meerada.app/gap/" in text
    assert "one-time message" in text and "פנייה חד-פעמית" in text and "149 ₪" in text
