"""Gap pages — one public page per business that Google lists for a question, saying how
often the AI engines name it (usually: never), who they name instead, which pages they
read for that question, and the steps that close the gap. The page is the lead's landing
page (the outreach mail links to it) and the inbound path (an owner searching their own
name finds it). Facts only: Google's position on a dated read, our measured counts, the
engines' cited sources. No consumer-style ratings are shown; the quality bar is stated in
words. Every page carries a correction/removal channel.

    meerada visibility gap --state visibility_state.json --out site/gap
"""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from handover.visibility.compare import compare
from handover.visibility.consensus import rank
from handover.visibility.google import DATA_DIR, load_snapshot
from handover.visibility.questions import QUESTIONS, Query
from handover.visibility.state import State

_HEB = re.compile(r"[֐-׿]")
_ASCII = re.compile(r"[^a-z0-9]+")
DISCLOSURE = (
    "Published by Meerada, an AI-visibility measurement service. The business did not pay "
    "and was not asked. The AI counts come from asking each engine the question above "
    "through its API with web search, several times; Google's position is from a dated read "
    "of the Google Maps result list. Nothing on this page is a review."
)


def slug_for(name: str, query_id: str, key: str) -> str:
    base = _ASCII.sub("-", name.lower()).strip("-")
    if len(base) >= 3:
        return f"{base[:60]}-{query_id}"
    return f"{query_id}-{hashlib.sha1(key.encode()).hexdigest()[:6]}"


def cited_hosts(answers: list[Any], limit: int = 6) -> list[tuple[str, int]]:
    hosts: Counter[str] = Counter()
    for a in answers:
        if a.error:
            continue
        for c in a.citations:
            host = urlparse(c if "://" in c else f"https://{c}").netloc.lower().removeprefix("www.")
            if host:
                hosts[host] += 1
    return hosts.most_common(limit)


def _chips(engines: dict[str, Any], labels: dict[str, str], runs_by_engine: dict[str, int]) -> str:
    out = []
    for e, n in runs_by_engine.items():
        named = int(engines.get(e, {}).get("named", 0)) if engines else 0
        out.append(
            f'<span class="chip{" on" if named else ""}">{escape(labels.get(e, e))} {named}/{n}</span>'
        )
    return "".join(out)


def render_gap_page(
    q: Query,
    row: dict[str, Any],
    ranking: dict[str, Any],
    cmp: dict[str, Any],
    hosts: list[tuple[str, int]],
    slug: str,
) -> str:
    name = row["name"]
    named, runs = int(row.get("named_runs", 0)), int(row.get("runs") or ranking["runs"])
    ai_rank = row.get("ai_rank")
    engines = ranking["results"][ai_rank - 1]["engines"] if ai_rank else {}
    heb = q.lang == "he" or bool(_HEB.search(name))
    headline = (
        f"Named in {named} of {runs} AI answers" if ai_rank else f"Named in 0 of {runs} AI answers"
    )
    sub = f"Google Maps #{row['google_rank']} for this question · {escape(cmp['google_label'])}"
    quality = row.get("quality")
    bar = (
        "Meets the quality bar for promotion."
        if quality
        else (
            "Below the quality bar — Meerada does not promote it until the reviews earn it."
            if quality is False
            else "Quality bar not assessed (no rating recorded)."
        )
    )
    instead = "".join(
        f'<li><div class="rank">{i}</div><div class="body"><div class="name">{escape(r["name"])}</div><div class="src">named in {r["named_runs"]} of {r["runs"]} runs</div></div></li>'
        for i, r in enumerate(ranking["results"][:5], start=1)
    )
    reads = ", ".join(f"{escape(h)} x{n}" for h, n in hosts) or "the business sites themselves"
    steps = "".join(f"<li>{escape(s)}</li>" for s in row.get("lift", []))
    q_enc = escape(q.text.replace(" ", "+"))
    cta = f"../search.html?q={q_enc}&business={escape(name.replace(' ', '+'))}#claim"
    he_line = ""
    if heb:
        he_line = (
            f'<p class="lede" dir="rtl">{escape(name)} מופיע ב-Google Maps במקום {row["google_rank"]} לשאלה הזו, '
            + (
                f"ונקוב ב-{named} מתוך {runs} תשובות ה-AI שמדדנו."
                if ai_rank
                else f"ולא נקוב באף אחת מ-{runs} תשובות ה-AI שמדדנו."
            )
            + " פיילוט חינם, בלי כרטיס אשראי: אנחנו מפרסמים עמוד ישות באנגלית ובעברית, בודקים נוכחות בעמודים שהמנועים מצטטים, ומודדים שוב כל שבוע.</p>"
        )
    title = f"{name} — {(headline[0].lower() + headline[1:])} · {q.city}"
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="canonical" href="https://meerada.app/gap/{escape(slug)}.html">
<link rel="icon" href="../logo.svg" type="image/svg+xml">
<meta name="description" content="{escape(name)}: Google Maps #{row["google_rank"]} for “{escape(q.text[:80])}”, {(headline[0].lower() + headline[1:])}. What the engines read instead, and the steps that close the gap.">
<meta property="og:title" content="{escape(title)}"><meta property="og:type" content="article">
<script src="../assets/family.js" defer></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<link rel="stylesheet" href="../assets/search.css">
</head><body><div class="wrap">
<div class="crumb"><a href="../s/{escape(q.id)}.html">← What the AI engines show for this question</a></div>
<h1>{escape(name)}</h1>
<p class="lede"><b>{headline}</b> to “{escape(q.text)}”. {sub}.</p>
{he_line}
<div class="chips">{_chips(engines, ranking["engine_labels"], ranking["engines"])}</div>
<div class="gap"><h2>Who the engines name instead</h2><ol class="results">{instead or '<li class="none">No option named by any engine yet.</li>'}</ol>
<p>For this question the engines cited: {reads}. A business that is not on those pages is not in the answer, however well it ranks on Google.</p></div>
<div class="lift"><div class="lift-head"><b>What closes the gap, in order</b></div><div class="bar-note">{bar}</div><ol class="steps">{steps}</ol>
<a class="cta" href="{cta}">Start a free pilot for {escape(name)} →</a>
<p class="s">One month, no card. Meerada publishes a factual entity page in English and the local language, checks the pages the engines cite for this question, sends the fix list, and re-measures every week. The before/after is published only with your permission.</p></div>
<div class="note">{escape(DISCLOSURE)} Run this business? Corrections or removal: hello@meerada.app — handled within a week.</div>
</div></body></html>
"""


def build_gap_pages(
    state: State, out_dir: Path, queries: tuple[Query, ...] = QUESTIONS, google_dir: Path = DATA_DIR
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_query: dict[str, list[Any]] = {}
    for a in state.answers:
        by_query.setdefault(a.query_id, []).append(a)
    leads: list[dict[str, Any]] = []
    written: list[Path] = []
    for q in queries:
        answers = by_query.get(q.id, [])
        snap = load_snapshot(q.id, google_dir)
        if snap is None or not any(not a.error for a in answers):
            continue
        ranking = rank(answers)
        cmp = compare(ranking, snap)
        if not cmp:
            continue
        hosts = cited_hosts(answers)
        for row in sorted(cmp["google_only"] + cmp["both"], key=lambda r: r["google_rank"]):
            key = next((g.key for g in snap.results if g.name == row["name"]), row["name"])
            slug = slug_for(row["name"], q.id, key)
            (out_dir / f"{slug}.html").write_text(
                render_gap_page(q, row, ranking, cmp, hosts, slug), encoding="utf-8"
            )
            written.append(out_dir / f"{slug}.html")
            leads.append(
                {
                    "slug": slug,
                    "business": row["name"],
                    "query_id": q.id,
                    "question": q.text,
                    "city": q.city,
                    "country": q.country,
                    "category": q.category,
                    "lang": q.lang,
                    "google_rank": row["google_rank"],
                    "quality": row.get("quality"),
                    "named_runs": int(row.get("named_runs", 0)),
                    "runs": int(row.get("runs") or ranking["runs"]),
                    "ai_rank": row.get("ai_rank"),
                    "website": row.get("website"),
                    "cited_hosts": [h for h, _ in hosts],
                    "google_read": snap.read_at,
                }
            )
    leads.sort(
        key=lambda r: (
            r["named_runs"] > 0,
            r["quality"] is not True,
            r["query_id"],
            r["google_rank"],
        )
    )
    (out_dir / "leads.json").write_text(
        json.dumps(
            {"generated_at": datetime.now(tz=UTC).isoformat(), "leads": leads},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    items = "".join(
        f'<li><a href="{escape(r["slug"])}.html">{escape(r["business"])}</a> <span class="s">· {escape(r["city"])} · Google #{r["google_rank"]} · AI {r["named_runs"]}/{r["runs"]}{" · below the quality bar" if r["quality"] is False else ""}</span></li>'
        for r in leads
    )
    (out_dir / "index.html").write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Listed on Google, missing from the AI answers</title><link rel="canonical" href="https://meerada.app/gap/"><link rel="icon" href="../logo.svg" type="image/svg+xml"><script src="../assets/family.js" defer></script><link rel="stylesheet" href="../assets/search.css"></head><body><div class="wrap"><div class="crumb"><a href="../search.html">← Search anything</a></div><h1>Listed on Google, missing from the AI answers</h1><p class="lede">{len(leads)} businesses from Google\'s own lists for the questions we measure, with how often the AI engines name each one. Most: never.</p><ul class="list">{items}</ul><div class="note">{escape(DISCLOSURE)}</div></div></body></html>',
        encoding="utf-8",
    )
    written += [out_dir / "leads.json", out_dir / "index.html"]
    return written
