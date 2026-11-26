"""Claims intake — "this is my business" rows from search.html become pilots.

The page inserts into Supabase ``search_claims`` (anonymous insert only). This module
reads the table through the management API (``SUPABASE_ACCESS_TOKEN``), keeps every row
with its contact fields in a private file outside git, matches the question to a measured
one, and appends a contact-free pilot stub to ``data/pilots.json`` — the same shape as the
experiment registry, so the weekly proof round and the report mails pick it up. Nothing is
sent to the owner from here; the stub says who to write to in the private file.

    meerada visibility claims --token-file private/supabase-token.txt
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from handover.visibility.api import match_question

PROJECT_REF = os.environ.get("MEERADA_SUPABASE_REF", "vytkiwibuohtcmjmslkh")
SQL = (
    "select id, created_at, kind, query, business, website, phone, contact, lang, page "
    "from search_claims where id > {after} order by id limit 500"
)
_SLUG = re.compile(r"[^a-z0-9]+")


def _post(url: str, token: str, body: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_claims(
    token: str, after: int = 0, ref: str = PROJECT_REF, post: Any = _post
) -> list[dict[str, Any]]:
    """Rows newer than ``after`` (an id), oldest first."""
    url = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    rows = post(url, token, {"query": SQL.format(after=int(after))})
    return [dict(r) for r in rows] if isinstance(rows, list) else []


def _domain(website: str) -> str:
    if not website:
        return ""
    host = urlparse(website if "://" in website else f"https://{website}").netloc.lower()
    return host.removeprefix("www.")


def _slug(business: str, claim_id: int) -> str:
    base = _SLUG.sub("-", business.lower()).strip("-")[:40]
    return base or f"claim-{claim_id}"


def pilot_stub(claim: dict[str, Any], today: str) -> dict[str, Any] | None:
    """An experiment-shaped record for a claim whose question we measure; None otherwise."""
    q = match_question((claim.get("query") or "").strip().lower())
    if q is None or not (claim.get("business") or "").strip():
        return None
    business = claim["business"].strip()
    return {
        "id": f"{q.id}-{_slug(business, int(claim['id']))}",
        "business": business,
        "aliases": [],
        "domain": _domain(claim.get("website") or ""),
        "queries": [q.id],
        "lever": "profile",
        "started": today,
        "city": q.city,
        "category": q.category,
        "control": False,
        "notes": f"claimed on search.html ({claim.get('kind') or 'claim'}, {str(claim.get('created_at') or today)[:10]}); contact in the private claims file (claim {claim['id']})",
    }


def _load(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return list(raw.get(key, []))


def intake(
    claims: list[dict[str, Any]], pilots_path: Path, contacts_path: Path, today: str | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Merge new rows into the private claims file and new stubs into the public pilots
    register. Returns (new claims, new pilots)."""
    today = today or datetime.now(tz=UTC).date().isoformat()
    known = _load(contacts_path, "claims")
    seen = {int(c["id"]) for c in known}
    new_claims = [c for c in claims if int(c["id"]) not in seen]
    pilots = _load(pilots_path, "experiments")
    have = {p["id"] for p in pilots}
    new_pilots = []
    for c in new_claims:
        stub = pilot_stub(c, today)
        if stub and stub["id"] not in have:
            pilots.append(stub)
            have.add(stub["id"])
            new_pilots.append(stub)
    if new_claims:
        contacts_path.parent.mkdir(parents=True, exist_ok=True)
        contacts_path.write_text(
            json.dumps({"claims": known + new_claims}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    if new_pilots:
        pilots_path.parent.mkdir(parents=True, exist_ok=True)
        pilots_path.write_text(
            json.dumps(
                {
                    "_method": "Pilots that claimed their business on search.html. Same shape as experiments.json; contacts live outside git (out/claims). Public case pages only with the owner's permission.",
                    "experiments": pilots,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    return new_claims, new_pilots


def last_claim_id(contacts_path: Path) -> int:
    return max((int(c["id"]) for c in _load(contacts_path, "claims")), default=0)
