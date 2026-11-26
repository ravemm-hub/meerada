"""Claims intake on a fake management-API response."""

from __future__ import annotations

import json
from pathlib import Path

from handover.visibility.claims import fetch_claims, intake, last_claim_id, pilot_stub

ROWS = [
    {
        "id": 7,
        "created_at": "2026-11-27T08:00:00+00:00",
        "kind": "claim",
        "query": "a plumber in tel aviv",
        "business": "Eitan Plumber",
        "website": "https://www.eitan-plumb.co.il/",
        "phone": "050-0000000",
        "contact": "x@example.com",
        "lang": "en",
        "page": "https://meerada.app/search.html?q=...",
    },
    {
        "id": 8,
        "created_at": "2026-11-27T09:00:00+00:00",
        "kind": "request",
        "query": "best sushi in oslo",
        "business": "Sushi Oslo",
        "website": "",
        "phone": "1",
        "contact": "",
        "lang": "en",
        "page": "",
    },
    {
        "id": 9,
        "created_at": "2026-11-27T10:00:00+00:00",
        "kind": "claim",
        "query": "tlv-electrician",
        "business": "אמנון חשמל",
        "website": "",
        "phone": "054",
        "contact": "",
        "lang": "he",
        "page": "",
    },
]


def test_fetch_uses_the_management_query_endpoint() -> None:
    def post(url: str, token: str, body: dict[str, object]) -> list[dict[str, object]]:
        assert url.endswith("/projects/vytkiwibuohtcmjmslkh/database/query") and token == "t"
        assert "where id > 6" in str(body["query"])
        return ROWS

    assert [r["id"] for r in fetch_claims("t", after=6, post=post)] == [7, 8, 9]


def test_pilot_stub_matches_measured_questions_only() -> None:
    stub = pilot_stub(ROWS[0], "2026-11-27")
    assert (
        stub is not None
        and stub["id"] == "tlv-plumber-eitan-plumber"
        and stub["domain"] == "eitan-plumb.co.il"
    )
    assert (
        stub["queries"] == ["tlv-plumber"] and stub["lever"] == "profile" and "contact" not in stub
    )
    assert pilot_stub(ROWS[1], "2026-11-27") is None  # not a question we measure
    heb = pilot_stub(ROWS[2], "2026-11-27")
    assert heb is not None and heb["id"] == "tlv-electrician-claim-9" and heb["city"] == "Tel Aviv"


def test_intake_keeps_contacts_private_and_dedupes(tmp_path: Path) -> None:
    pilots, contacts = tmp_path / "data" / "pilots.json", tmp_path / "out" / "claims.json"
    new_c, new_p = intake(ROWS, pilots, contacts, "2026-11-27")
    assert [c["id"] for c in new_c] == [7, 8, 9] and [p["id"] for p in new_p] == [
        "tlv-plumber-eitan-plumber",
        "tlv-electrician-claim-9",
    ]
    public = pilots.read_text(encoding="utf-8")
    assert (
        "x@example.com" not in public and "050-0000000" not in public and "Eitan Plumber" in public
    )
    assert "x@example.com" in contacts.read_text(encoding="utf-8")
    assert last_claim_id(contacts) == 9
    again_c, again_p = intake([*ROWS, {**ROWS[0], "id": 10}], pilots, contacts, "2026-11-28")
    assert [c["id"] for c in again_c] == [
        10
    ] and again_p == []  # same business, same question: one pilot
    assert len(json.loads(pilots.read_text(encoding="utf-8"))["experiments"]) == 2
