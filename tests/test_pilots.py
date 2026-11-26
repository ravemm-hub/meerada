"""Weekly pilot proof and the profile draft, on fixtures only."""

# ruff: noqa: E501

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from handover.visibility.experiments import load_experiments
from handover.visibility.pilots import build_pilot_reports, summarize
from handover.visibility.profile_draft import draft_profile, write_draft
from handover.visibility.state import Answer, State

NOW = datetime(2026, 12, 8, 9, tzinfo=UTC)


def _answer(engine: str, when: datetime, names: list[str]) -> Answer:
    return Answer(
        engine=engine,
        model="m",
        query_id="ldn-yoga",
        asked_at=when,
        text="",
        citations=["https://foldyoga.co.uk/classes"] if "Fold" in " ".join(names) else [],
        names=names,
        name_keys=[n.lower() for n in names],
    )


def _registry(tmp_path: Path) -> Path:
    reg = {
        "experiments": [
            {
                "id": "ldn-yoga-fold",
                "business": "Fold Yoga London",
                "aliases": ["Fold Yoga"],
                "domain": "foldyoga.co.uk",
                "queries": ["ldn-yoga"],
                "lever": "guide",
                "started": "2026-11-26",
                "city": "London",
                "category": "yoga",
            },
            {
                "id": "ldn-yoga-ctrl",
                "business": "Yogahome",
                "queries": ["ldn-yoga"],
                "lever": "none",
                "control": True,
                "started": "2026-11-26",
                "city": "London",
                "category": "yoga",
            },
        ]
    }
    p = tmp_path / "experiments.json"
    p.write_text(json.dumps(reg), encoding="utf-8")
    return p


def _state() -> State:
    before = NOW - timedelta(days=13)
    week = NOW - timedelta(days=2)
    answers = [_answer("chatgpt", before, ["Triyoga"]) for _ in range(7)]
    answers += [_answer("chatgpt", week, ["Triyoga", "Fold Yoga London"]) for _ in range(3)]
    answers += [_answer("chatgpt", week, ["Triyoga"]) for _ in range(4)]
    return State(answers=answers)


def test_summarize_counts_baseline_and_latest_week(tmp_path: Path) -> None:
    pilots = summarize(load_experiments(_registry(tmp_path)), _state(), NOW)
    fold = next(p for p in pilots if p["id"] == "ldn-yoga-fold")
    assert fold["week"] == 2
    assert fold["baseline"] == {
        "named": 0,
        "n": 7,
        "per_engine": {"chatgpt": {"n": 7, "named": 0, "cited": 0}},
    }
    assert fold["latest_week"]["named"] == 3 and fold["latest_week"]["n"] == 7
    assert fold["latest_week"]["per_engine"]["chatgpt"]["cited"] == 3
    assert round(fold["change"], 3) == 0.429
    ctrl = next(p for p in pilots if p["control"])
    assert ctrl["latest_week"]["named"] == 0


def test_pilot_reports_write_digest_and_mails(tmp_path: Path) -> None:
    out = tmp_path / "pilots"
    written = build_pilot_reports(_registry(tmp_path), _state(), out, NOW)
    assert [w.name for w in written] == ["pilots.json", "digest.md", "ldn-yoga-fold.md"]
    digest = (out / "digest.md").read_text(encoding="utf-8")
    assert "| Fold Yoga London | guide | 2 | 0/7 | 3/7 | +43% |" in digest
    assert (
        "Yogahome (control)" in digest and "1 of 1 pilots named at least once this week." in digest
    )
    mail = (out / "ldn-yoga-fold.md").read_text(encoding="utf-8")
    assert (
        "Week 2" in mail and "named in 0 of 7 answers" in mail and "named in 3 of 7 answers" in mail
    )
    assert "The engines have started naming you." in mail and "שבוע 2" in mail


def test_profile_draft_reads_the_page_and_marks_everything_to_confirm(tmp_path: Path) -> None:
    html = (
        '<html lang="he"><head><title>Amnon Electric | חשמלאי מוסמך</title>'
        '<meta name="description" content="Licensed electrician in Tel Aviv, fuse boxes and emergency calls since 2009."></head>'
        "<body><h1>Amnon Electric</h1><h2>Fuse box replacement</h2><h2>Emergency electrician 24/7</h2>"
        "<p>Call 054-534-8987 or amnon@example.co.il. Nakhum Sokolov St 88, Tel Aviv. Open Sun-Thu 8:00-20:00.</p>"
        '<a href="https://www.instagram.com/amnonelectric/">Instagram</a></body></html>'
    )

    def fetch(url: str) -> tuple[int, dict[str, str], str]:
        assert url == "https://amnon.example"
        return 200, {}, html

    d = draft_profile("amnon.example", city="Tel Aviv", category="electrician", fetch=fetch)
    assert d["name"] == "Amnon Electric" and d["slug"] == "amnon-electric-tel-aviv"
    assert (
        d["phone"] == "054-534-8987"
        and "Sokolov St 88" in d["address"]
        and "Sun-Thu 8:00-20:00" in d["hours"]
    )
    assert d["services"][:2] == ["Amnon Electric", "Fuse box replacement"] and d["languages"] == [
        "he"
    ]
    assert (
        d["extras"][0] == "e-mail: amnon@example.co.il"
        and "instagram.com/amnonelectric" in d["extras"][1]
    )
    assert "phone" in d["_confirm"] and d["_note"].startswith("DRAFT")
    path = write_draft(d, tmp_path / "drafts")
    assert (
        path.name == "amnon-electric-tel-aviv.json"
        and json.loads(path.read_text(encoding="utf-8"))["profiles"][0]["website"]
        == "https://amnon.example"
    )
