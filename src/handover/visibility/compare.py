"""AI side vs Google side for one question, and what closes the gap.

``compare(ranking, snapshot)`` joins the consensus ranking (what the AI engines name) with
Google's list for the same question:

* ``both``        — named by the engines and in Google's list
* ``google_only`` — in Google's list, never named by any engine in n runs: invisible to AI
* ``ai_only``     — named by the engines but not in Google's top list

For every invisible business the ``lift`` says, from the data of this question, what the
named options have that it does not: which page families the engines cite here, and the
order of steps. A business under the quality bar (rating / review count) is marked and is
not promoted, whatever it pays.
"""

from __future__ import annotations

import re
from collections import Counter
from html import escape
from typing import Any

from handover.visibility.extract import normalize
from handover.visibility.google import QUALITY_MIN_RATING, QUALITY_MIN_REVIEWS, GoogleSnapshot

# Words that say what or where a business is, not which one it is. Two names that share
# only these are not the same business ("City Dental Group NYC" is not "Sachar Dental NY").
GENERIC = frozenset(
    re.split(
        r"\s+",
        "the and of in at for dental dentist dentistry clinic yoga studio pilates salon hair "
        "hairdresser barber plumber plumbing plumbers restaurant pizzeria trattoria cafe coffee "
        "gym fitness center centre group office practice london nyc new york city tel aviv "
        "manhattan brooklyn soho ltd inc llc co dr",
    )
)


def _distinct(key: str, ignore: frozenset[str]) -> set[str]:
    return {t for t in key.split() if len(t) > 1 and t not in ignore}


def same_business(a: str, b: str, ignore: frozenset[str] = GENERIC) -> bool:
    """Same business when the distinctive words (not category, not city) of one name are
    all in the other, or most of them are (``Oca London`` ~ ``Oca Yoga London``)."""
    ka, kb = normalize(a), normalize(b)
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    ta, tb = _distinct(ka, ignore), _distinct(kb, ignore)
    if not ta or not tb:
        return False
    shared = ta & tb
    if not shared:
        return False
    return ta <= tb or tb <= ta or len(shared) / min(len(ta), len(tb)) >= 0.6


def _lift_steps(cited: list[tuple[str, int]], quality: bool | None) -> list[str]:
    families = ", ".join(f for f, _ in cited[:3]) or "the business sites themselves"
    steps = [
        f"Be where the engines read for this question: they cite {families}. "
        "A page about you on those sources is what gets a name into the answer.",
        "Make your own site readable to an engine: a plain text description of what you do, "
        "where, for whom, with prices and opening hours in the HTML (not only in images).",
        "One consistent name, address and phone everywhere the engines look "
        "(Google, directories, your site), so the mentions add up to one business.",
        "Re-measure: we ask the same question again on every engine and show the change, "
        "run by run.",
    ]
    if quality is False:
        steps.insert(
            0,
            f"Quality bar first: under {QUALITY_MIN_RATING}★ or fewer than "
            f"{QUALITY_MIN_REVIEWS} reviews we do not promote a business. Earn the reviews; "
            "the rest follows.",
        )
    return steps


def compare(ranking: dict[str, Any], snapshot: GoogleSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None or not snapshot.results:
        return None
    ai = ranking.get("results", [])
    runs = int(ranking.get("runs", 0))
    cited: Counter[str] = Counter()
    for r in ai:
        for s in r.get("sources", []):
            cited[s] += 1
    both: list[dict[str, Any]] = []
    google_only: list[dict[str, Any]] = []
    matched_ai: set[str] = set()
    for g in snapshot.results:
        hit = next((r for r in ai if same_business(g.name, r["name"])), None)
        row: dict[str, Any] = {
            "name": g.name,
            "google_rank": g.rank,
            "rating": g.rating,
            "reviews": g.reviews,
            "website": g.website,
            "quality": g.meets_quality_bar,
        }
        if hit is not None:
            matched_ai.add(hit["key"])
            both.append(
                {
                    **row,
                    "ai_rank": ai.index(hit) + 1,
                    "ai_name": hit["name"],
                    "named_runs": hit["named_runs"],
                    "runs": hit["runs"],
                }
            )
        else:
            google_only.append(
                {
                    **row,
                    "named_runs": 0,
                    "runs": runs,
                    "lift": _lift_steps(cited.most_common(), g.meets_quality_bar),
                }
            )
    ai_only = [
        {"name": r["name"], "ai_rank": i, "named_runs": r["named_runs"], "runs": r["runs"]}
        for i, r in enumerate(ai, start=1)
        if r["key"] not in matched_ai
    ]
    n = len(snapshot.results)
    return {
        "google_label": snapshot.label,
        "google_query": snapshot.query,
        "google_count": n,
        "both": both,
        "google_only": google_only,
        "ai_only": ai_only,
        "invisible_share": round(len(google_only) / n, 3) if n else 0.0,
        "cited_families": [f for f, _ in cited.most_common(4)],
        "runs": runs,
    }


def _stars(row: dict[str, Any]) -> str:
    if row.get("rating") is None:
        return ""
    return f'<span class="g-rating">{row["rating"]}★ ({row.get("reviews") or 0})</span>'


def render_compare(cmp: dict[str, Any], claim_href: str) -> tuple[str, str]:
    """(Google column, gap block with the lift cards) as HTML for a query page."""
    rows = []
    for row in sorted(cmp["both"] + cmp["google_only"], key=lambda r: r["google_rank"]):
        if row.get("ai_rank"):
            tag = (
                f'<span class="tag on">AI #{row["ai_rank"]} · '
                f"{row['named_runs']}/{row['runs']}</span>"
            )
        else:
            tag = f'<span class="tag off">invisible to AI · 0/{row["runs"]}</span>'
        rows.append(
            f'<li><div class="rank">{row["google_rank"]}</div><div class="body">'
            f'<div class="name">{escape(row["name"])} {_stars(row)}</div>{tag}</div></li>'
        )
    inv = cmp["google_only"]
    gap = (
        f"<b>{len(inv)} of Google's top {cmp['google_count']}</b> never appear in any AI answer "
        f"({cmp['runs']} runs)."
        if inv
        else f"Every one of Google's top {cmp['google_count']} is named by at least one engine."
    )
    cards = "".join(
        f'<div class="lift"><div class="lift-head"><b>{escape(b["name"])}</b> {_stars(b)} '
        f'<span class="s">Google #{b["google_rank"]} · AI 0/{b["runs"]}</span></div>'
        + (
            '<div class="bar-note">Below the quality bar — not promoted.</div>'
            if b.get("quality") is False
            else ""
        )
        + '<ol class="steps">'
        + "".join(f"<li>{escape(s)}</li>" for s in b["lift"])
        + f'</ol><a class="cta" href="{claim_href}&business={escape(b["name"].replace(" ", "+"))}">'
        f"Lift this business →</a></div>"
        for b in inv[:5]
    )
    column = (
        f'<div class="col google"><h2>What Google shows</h2>'
        f'<div class="meta">{escape(cmp["google_label"])} · “{escape(cmp["google_query"])}”</div>'
        f'<ol class="results g">{"".join(rows)}</ol></div>'
    )
    gap_block = (
        f'<div class="gap"><h2>The gap</h2><p>{gap} The engines for this question cite '
        f"{escape(', '.join(cmp['cited_families']) or 'the business sites')}; a business that is "
        f"not on those pages is not in the answer, however well it ranks on Google.</p>"
        f"{cards}</div>"
    )
    return column, gap_block


NO_GOOGLE = (
    '<div class="col google"><h2>What Google shows</h2>'
    '<p class="s">Not recorded yet for this question.</p></div>'
)
