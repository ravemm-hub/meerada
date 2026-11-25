"""Pick test-case candidates from the middle of Google's results (Places API, New).

    python scripts/select_businesses.py --key-file private/google-places.txt \
        --query "plumber in Tel Aviv" --n 3 --seed 7

Rule (docs/SEARCH-ENGINE-RESEARCH.md §5ג): positions 8-20 for the category in the city,
rating >= 4.3 with >= 10 reviews (below that the reviews gate blocks any lever — not a test
of the engine), a website (so a factual profile is possible). Prints JSON lines; ratings are
for selection only and never published. Needs "Places API (New)" enabled for the key.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = (
    "places.id,places.displayName,places.rating,places.userRatingCount,places.websiteUri,"
    "places.formattedAddress,places.nationalPhoneNumber,places.regularOpeningHours.weekdayDescriptions"
)


def search(key: str, query: str, page_token: str = "") -> dict[str, Any]:
    body: dict[str, Any] = {"textQuery": query, "pageSize": 20}
    if page_token:
        body["pageToken"] = page_token
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELDS + ",nextPageToken",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data: dict[str, Any] = json.loads(resp.read().decode())
            return data
    except urllib.error.HTTPError as exc:
        sys.exit(f"Places API {exc.code}: {exc.read().decode(errors='replace')[:300]}")


def candidates(
    places: list[dict[str, Any]], lo: int, hi: int, min_rating: float, min_reviews: int
) -> list[dict[str, Any]]:
    out = []
    for pos, p in enumerate(places, start=1):
        if pos < lo or pos > hi:
            continue
        rating = float(p.get("rating") or 0)
        reviews = int(p.get("userRatingCount") or 0)
        if rating < min_rating or reviews < min_reviews or not p.get("websiteUri"):
            continue
        out.append(
            {
                "position": pos,
                "name": (p.get("displayName") or {}).get("text", ""),
                "website": p.get("websiteUri", ""),
                "address": p.get("formattedAddress", ""),
                "phone": p.get("nationalPhoneNumber", ""),
                "hours": "; ".join(
                    (p.get("regularOpeningHours") or {}).get("weekdayDescriptions") or []
                ),
                "rating_for_selection_only": rating,
                "reviews_for_selection_only": reviews,
                "place_id": p.get("id", ""),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", type=Path, required=True)
    ap.add_argument("--query", required=True, help='e.g. "plumber in Tel Aviv"')
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--lo", type=int, default=8)
    ap.add_argument("--hi", type=int, default=20)
    ap.add_argument("--min-rating", type=float, default=4.3)
    ap.add_argument("--min-reviews", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    key = args.key_file.read_text(encoding="utf-8").strip()
    data = search(key, args.query)
    places = list(data.get("places") or [])
    token = data.get("nextPageToken")
    if token and len(places) < args.hi:
        places += list(search(key, args.query, token).get("places") or [])
    pool = candidates(places, args.lo, args.hi, args.min_rating, args.min_reviews)
    rng = random.Random(args.seed)
    chosen = rng.sample(pool, min(args.n, len(pool)))
    print(
        f"# {args.query}: {len(places)} results, {len(pool)} eligible "
        f"in positions {args.lo}-{args.hi}",
        file=sys.stderr,
    )
    for c in chosen:
        print(json.dumps(c, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
