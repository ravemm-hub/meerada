"""Profile pages in the Meerada index."""

from __future__ import annotations

import json
from pathlib import Path

from handover.visibility.profiles import Profile, build_profiles, render_profile


def _profile() -> Profile:
    return Profile(
        id="tlv-italian-gusto",
        name="Gusto",
        slug="gusto-tel-aviv",
        city="Tel Aviv",
        country="Israel",
        category="Italian restaurant",
        website="https://gusto.co.il",
        phone="03-000-0000",
        address="Frishman St 90",
        hours="Sun-Sat 12:00-23:00",
        summary="Italian restaurant on Frishman Street.",
        services=["pizza", "pasta"],
        prices="pizzas 70-90 ILS",
        booking="ontopo",
        people=["A. Chef — chef"],
        sources=["https://gusto.co.il", "https://gusto.co.il/menu"],
        checked="2026-11-25",
        discrepancies="Maps closes 11 pm; site says kitchen closes 22:30.",
    )


def test_profile_renders_facts_disclosure_jsonld_and_no_ratings() -> None:
    html = render_profile(_profile())
    assert (
        "Gusto" in html
        and "Frishman St 90" in html
        and "did not pay and were not consulted" in html
    )
    assert '"@type": "LocalBusiness"' in html and '"telephone": "03-000-0000"' in html
    assert (
        "Discrepancy noted" in html and "star" not in html.lower() and "rating" not in html.lower()
    )
    assert 'href="../assets/family.js"' not in html and 'src="../assets/family.js"' in html


def test_build_profiles_writes_pages_and_index(tmp_path: Path) -> None:
    data = tmp_path / "profiles"
    data.mkdir()
    (data / "p.json").write_text(
        json.dumps({"profiles": [json.loads(_profile().model_dump_json())]}), encoding="utf-8"
    )
    written = build_profiles(data, tmp_path / "b")
    assert [p.name for p in written] == ["gusto-tel-aviv.html", "index.html"]
    assert "Business profiles" in (tmp_path / "b" / "index.html").read_text(encoding="utf-8")
