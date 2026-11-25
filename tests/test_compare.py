"""AI side vs Google side: Maps snapshot parsing, business matching, the gap and the lift."""

from __future__ import annotations

import json
from pathlib import Path

from handover.visibility.compare import compare, render_compare, same_business
from handover.visibility.google import (
    GoogleResult,
    GoogleSnapshot,
    load_snapshot,
    parse_maps_text,
    places_search,
)

MAPS_TEXT = """Results
Wally Health
Sponsored

Wally Health
4.7(840)
Dentist · 249 Church Street
209 NYC Dental
209 NYC Dental
4.8(1,936)
Dentist ·  · 209 E 56th St 1st floor
Open · Closes 6:30 pm
New York Dental Office
New York Dental Office
4.9(480)
Dentist ·  · 245 E 63rd St #110
Fresh Smile
Fresh Smile
No reviews
Dentist · Broadway
Update results when map moves
"""


def test_parse_maps_text_skips_ads_and_reads_ratings() -> None:
    res = parse_maps_text(MAPS_TEXT)
    assert [r.name for r in res] == ["209 NYC Dental", "New York Dental Office", "Fresh Smile"]
    assert res[0].rating == 4.8 and res[0].reviews == 1936 and res[0].category == "Dentist"
    assert res[2].rating is None and res[2].meets_quality_bar is None
    assert res[0].meets_quality_bar is True
    assert GoogleResult(rank=1, name="X", rating=4.0, reviews=500).meets_quality_bar is False


def test_snapshot_roundtrip_and_label(tmp_path: Path) -> None:
    snap = GoogleSnapshot(
        query_id="q1",
        query="dentist NYC",
        locale="en-IL",
        read_at="2026-11-25",
        results=parse_maps_text(MAPS_TEXT),
    )
    (tmp_path / "q1.json").write_text(json.dumps(snap.model_dump()), encoding="utf-8")
    back = load_snapshot("q1", tmp_path)
    assert back is not None and back.results[1].key == "new york dental office"
    assert back.label == "Google Maps from IL on 2026-11-25"
    assert load_snapshot("missing", tmp_path) is None


def test_places_search_maps_fields() -> None:
    def post(url: str, headers: dict[str, str], body: dict[str, object]) -> dict[str, object]:
        assert "X-Goog-FieldMask" in headers and body["textQuery"] == "yoga London"
        return {
            "places": [
                {
                    "displayName": {"text": "Triyoga"},
                    "rating": 4.6,
                    "userRatingCount": 900,
                    "websiteUri": "https://triyoga.co.uk",
                },
                {"rating": 5.0},
            ]
        }

    snap = places_search("yoga London", "k", post=post)
    assert snap.source == "places_api" and len(snap.results) == 1
    assert snap.results[0].website == "https://triyoga.co.uk" and snap.results[0].rank == 1


def test_same_business_ignores_category_and_city_words() -> None:
    assert same_business("Oca London", "Oca Yoga London")
    assert same_business("MoreYoga Soho", "MoreYoga")
    assert same_business("Pearl Dental NYC", "Pearl Dental")
    assert not same_business("City Dental Group NYC", "Sachar Dental NY")
    assert not same_business("Studio Hafif", "Dawn Hair Design")
    assert not same_business("Yoga Studio", "Yoga Studio London")  # nothing distinctive


def _ranking() -> dict[str, object]:
    def r(name: str, runs_named: int) -> dict[str, object]:
        return {
            "name": name,
            "key": name.lower(),
            "score": 0.1,
            "named_runs": runs_named,
            "runs": 10,
            "best_position": 1,
            "engines": {},
            "sources": ["Google", "Reviews & directories"],
        }

    return {"runs": 10, "results": [r("Triyoga", 8), r("Oca London", 5), r("Mudra Yoga", 2)]}


def test_compare_splits_both_google_only_and_ai_only() -> None:
    snap = GoogleSnapshot(
        query_id="ldn-yoga",
        query="yoga studio London",
        locale="en-IL",
        read_at="2026-11-25",
        results=[
            GoogleResult(rank=1, name="Oca Yoga London", rating=4.9, reviews=120),
            GoogleResult(rank=2, name="Brewer Street Yoga", rating=5.0, reviews=105),
            GoogleResult(rank=3, name="Tiny Yoga", rating=3.9, reviews=4),
        ],
    )
    cmp = compare(_ranking(), snap)
    assert cmp is not None
    assert [b["name"] for b in cmp["both"]] == ["Oca Yoga London"]
    assert cmp["both"][0]["ai_rank"] == 2 and cmp["both"][0]["named_runs"] == 5
    assert [g["name"] for g in cmp["google_only"]] == ["Brewer Street Yoga", "Tiny Yoga"]
    assert [a["name"] for a in cmp["ai_only"]] == ["Triyoga", "Mudra Yoga"]
    assert cmp["invisible_share"] == 0.667 and cmp["cited_families"][0] == "Google"
    brewer, tiny = cmp["google_only"]
    assert brewer["quality"] is True and "cite Google" in brewer["lift"][0]
    assert tiny["quality"] is False and tiny["lift"][0].startswith("Quality bar first")
    col, gap = render_compare(cmp, "../search.html?q=yoga")
    assert "What Google shows" in col and "invisible to AI · 0/10" in col and "AI #2 · 5/10" in col
    assert "2 of Google's top 3" in gap and "Below the quality bar" in gap
    assert "business=Brewer+Street+Yoga" in gap
    assert compare(_ranking(), None) is None
