"""What Google shows for the same question — the other side of the comparison.

Two sources, same shape:

* ``data/google/<query_id>.json`` — a recorded snapshot of the Google Maps result list
  for a measured question (read by hand on a date, from a stated country). Used for the
  lab questions, so the pages never depend on a key.
* Places API (New) Text Search — live, for any question, when ``GOOGLE_API_KEY`` is set
  and the key has the Places API enabled. One request per question, ~$0.035.

Google's local pack is what people see for a local question; organic results differ and
are not what this module records. Every snapshot says where and when it was read.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from handover.visibility.extract import normalize

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "google"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELDS = (
    "places.displayName,places.rating,places.userRatingCount,places.websiteUri,"
    "places.googleMapsUri,places.formattedAddress"
)
PLACES_EST_USD = Decimal("0.035")  # Text Search, Enterprise SKU (rating + website)
QUALITY_MIN_RATING = 4.3
QUALITY_MIN_REVIEWS = 20

Post = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class GoogleResult(BaseModel):
    rank: int
    name: str
    key: str = ""
    rating: float | None = None
    reviews: int | None = None
    website: str | None = None
    maps_url: str | None = None
    category: str | None = None

    def model_post_init(self, _ctx: Any) -> None:
        if not self.key:
            self.key = normalize(self.name)

    @property
    def meets_quality_bar(self) -> bool | None:
        """None when Google shows no rating; else the bar every promoted business clears."""
        if self.rating is None or self.reviews is None:
            return None
        return self.rating >= QUALITY_MIN_RATING and self.reviews >= QUALITY_MIN_REVIEWS


class GoogleSnapshot(BaseModel):
    query_id: str
    query: str
    source: str = "google_maps"  # google_maps | places_api
    locale: str = ""  # e.g. "en-IL": interface language, country the search ran from
    read_at: str = ""  # YYYY-MM-DD
    method: str = ""  # how it was read, in words
    results: list[GoogleResult] = Field(default_factory=list)

    @property
    def label(self) -> str:
        src = "Google Maps" if self.source == "google_maps" else "Google Places API"
        where = f" from {self.locale.split('-')[-1]}" if "-" in self.locale else ""
        when = f" on {self.read_at}" if self.read_at else ""
        return f"{src}{where}{when}"


def load_snapshot(query_id: str, data_dir: Path = DATA_DIR) -> GoogleSnapshot | None:
    p = data_dir / f"{query_id}.json"
    if not p.exists():
        return None
    return GoogleSnapshot.model_validate(json.loads(p.read_text(encoding="utf-8")))


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        out: dict[str, Any] = json.loads(resp.read().decode())
    return out


def places_search(
    text: str, api_key: str, lang: str = "en", post: Post = _post, limit: int = 10
) -> GoogleSnapshot:
    """Places API (New) Text Search for ``text``: the list Google ranks for that phrase."""
    raw = post(
        PLACES_URL,
        {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": PLACES_FIELDS},
        {"textQuery": text, "languageCode": lang, "pageSize": limit},
    )
    results = [
        GoogleResult(
            rank=i,
            name=str((p.get("displayName") or {}).get("text") or "").strip(),
            rating=p.get("rating"),
            reviews=p.get("userRatingCount"),
            website=p.get("websiteUri"),
            maps_url=p.get("googleMapsUri"),
        )
        for i, p in enumerate(raw.get("places", [])[:limit], start=1)
        if (p.get("displayName") or {}).get("text")
    ]
    return GoogleSnapshot(
        query_id="live",
        query=text,
        source="places_api",
        locale=lang,
        method="Places API (New) Text Search",
        results=results,
    )


def maps_query(category: str, city: str) -> str:
    """The short phrase a person types into Google for a lab question."""
    return f"{category} {city}".strip()


_RATING = re.compile(r"^(?P<rating>\d\.\d)\((?P<reviews>\d[\d,]*)\)")


def parse_maps_text(text: str, limit: int = 10) -> list[GoogleResult]:
    """Read the Google Maps result list as rendered text: a name line, then
    ``4.7(312)`` (or ``No reviews``), then the category. Sponsored entries are skipped —
    they are ads, not Google's ranking."""
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[GoogleResult] = []
    seen: set[str] = set()
    for i, ln in enumerate(lines):
        m = _RATING.match(ln)
        if not m and ln != "No reviews":
            continue
        prev = [p for p in lines[max(0, i - 4) : i] if p]
        if not prev or "Sponsored" in prev:
            continue
        name = prev[-1].split(" · ")[0].strip()
        key = normalize(name)
        if not key or key in seen or len(name) > 90:
            continue
        seen.add(key)
        cat = lines[i + 1].split(" ·")[0].strip() if i + 1 < len(lines) else ""
        out.append(
            GoogleResult(
                rank=len(out) + 1,
                name=name,
                rating=float(m.group("rating")) if m else None,
                reviews=int(m.group("reviews").replace(",", "")) if m else 0,
                category=cat or None,
            )
        )
        if len(out) >= limit:
            break
    return out
