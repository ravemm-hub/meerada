"""The home page generator and the fix kit, on fixtures only."""

from __future__ import annotations

import json
from pathlib import Path

from handover.visibility.audit import Audit, Check
from handover.visibility.fixkit import render_fixkit
from handover.visibility.home import build_home, stats


def _question(
    qid: str, invisible: int, total: int, runs: int, lang: str = "en"
) -> dict[str, object]:
    google_only = [
        {
            "name": f"G{i}",
            "google_rank": i,
            "named_runs": 0,
            "runs": runs,
            "quality": True,
            "lift": ["x"],
        }
        for i in range(1, invisible + 1)
    ]
    both = [
        {
            "name": f"B{i}",
            "google_rank": invisible + i,
            "ai_rank": i,
            "named_runs": 3,
            "runs": runs,
            "quality": True,
        }
        for i in range(1, total - invisible + 1)
    ]
    return {
        "id": qid,
        "text": f"question {qid}",
        "lang": lang,
        "runs": runs,
        "engines": {"chatgpt": runs},
        "results": [
            {"name": "B1", "named_runs": 3, "runs": runs},
            {"name": "X", "named_runs": 1, "runs": runs},
        ],
        "comparison": {
            "google_only": google_only,
            "both": both,
            "google_count": total,
            "runs": runs,
            "invisible_share": round(invisible / total, 3),
        },
    }


def test_home_builds_cards_and_headline_numbers(tmp_path: Path) -> None:
    pages = tmp_path / "s"
    pages.mkdir()
    (pages / "a.json").write_text(json.dumps(_question("a", 9, 9, 23)), encoding="utf-8")
    (pages / "b.json").write_text(json.dumps(_question("b", 2, 5, 23, "he")), encoding="utf-8")
    (pages / "c.json").write_text(
        json.dumps(
            {
                "id": "c",
                "text": "no google side",
                "runs": 2,
                "engines": {"claude": 2},
                "results": [],
            }
        ),
        encoding="utf-8",
    )
    (pages / "index.json").write_text("{}", encoding="utf-8")
    s = stats(
        [
            json.loads(p.read_text(encoding="utf-8"))
            for p in pages.glob("*.json")
            if p.name != "index.json"
        ]
    )
    assert s == {
        "questions": 3,
        "answers": 48,
        "engines": 2,
        "google_listed": 14,
        "invisible": 11,
        "invisible_pct": 79,
    }
    out = build_home(pages, tmp_path / "index.html")
    html = out.read_text(encoding="utf-8")
    assert html.count('class="card"') == 2 and html.index('href="s/a.html"') < html.index(
        'href="s/b.html"'
    )
    assert "9 of Google's 9 never named" in html and 'dir="rtl"' in html
    assert (
        "<b>79%</b>" in html
        and "$29" in html
        and "'/search?q='" in html
        and "search_claims" in html
    )
    assert "the only engine that measures" in html and "4.3★ or 20 reviews" in html


def test_fixkit_lists_facts_changes_and_pages() -> None:
    exp = {
        "id": "tlv-electrician-amnon",
        "business": "אמנון חשמל",
        "aliases": ["Amnon Electric"],
        "domain": "amnon.example",
        "queries": ["tlv-electrician"],
    }
    a = Audit(
        url="https://amnon.example",
        name="אמנון חשמל",
        status=200,
        checks=[
            Check("prices", "Prices", False, 5, "", "Show prices or ranges."),
            Check("phone", "Phone", True, 5),
        ],
    )
    draft = {
        "name": "Amnon Electric",
        "phone": "054-534-8987",
        "address": "",
        "hours": "Sun-Thu 8-20",
        "services": ["Fuse boxes"],
        "languages": ["he"],
        "summary": "Licensed electrician in Tel Aviv.",
    }
    text = render_fixkit(
        exp,
        a,
        ["Be where the engines read"],
        [("google.com", 6), ("easy.co.il", 2)],
        draft,
        "2026-11-27",
    )
    assert "# Fix kit for אמנון חשמל" in text and "English form: Amnon Electric" in text
    assert "- Phone: 054-534-8987" in text and "- Address: TODO" in text
    assert "1. Show prices or ranges." in text and "Entity audit score today: 50/100" in text
    assert (
        "google.com (cited 6x): Google Business Profile" in text
        and "easy.co.il (cited 2x): easy.co.il: claim the listing" in text
    )
    assert (
        "> Licensed electrician in Tel Aviv. Services: Fuse boxes." in text
        and "- Be where the engines read" in text
    )
    unreachable = render_fixkit(exp, None, [], [], None, "2026-11-27")
    assert "could not be fetched" in unreachable and "- Phone: TODO" in unreachable
