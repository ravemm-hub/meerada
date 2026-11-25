"""Static query pages — one page per question the lab has answers for, ranked by the
consensus score, plus ``s/index.json`` (what the search box loads for instant results)
and a per-question JSON the page itself renders from.

    meerada visibility pages --state visibility_state.json --out site/s
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from handover.visibility.compare import NO_GOOGLE, compare, render_compare
from handover.visibility.consensus import rank
from handover.visibility.google import DATA_DIR, load_snapshot
from handover.visibility.questions import INTENT_LABELS, QUESTIONS, Query
from handover.visibility.state import State

_HEB = re.compile(r"[֐-׿]")

PAGE = """<!doctype html><html lang="{lang}"{rtl}><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="canonical" href="https://meerada.app/s/{slug}.html">
<link rel="icon" href="../logo.svg" type="image/svg+xml">
<meta name="description" content="{description}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{description}"><meta property="og:type" content="article">
<meta property="article:modified_time" content="{updated}">
<script type="application/ld+json">{jsonld}</script>
<script src="../assets/family.js" defer></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<link rel="stylesheet" href="../assets/search.css">
</head><body><div class="wrap">
<div class="crumb"><a href="../search.html">← Search anything</a></div>
<h1>{h1}</h1>
<p class="lede">{lede}</p>
<div class="meta">{meta}</div>
<div class="cols">
<div class="col ai"><h2>What the AI engines show</h2><ol class="results">{rows}</ol></div>
{google_col}
</div>
{gap}
<div class="claim" id="claim">
  <h2>Is your business here?</h2>
  <p>If it is not in this list, the AI engines are not recommending it for this question. <a href="../search.html?q={q_enc}#claim">Check your business and get the report</a> — what the engines read for this category, and what to fix, in order.</p>
</div>
<div class="note">{note}</div>
</div></body></html>
"""


def _row(i: int, r: dict[str, Any], labels: dict[str, str]) -> str:
    chips = "".join(
        f'<span class="chip{" on" if v["named"] else ""}" title="{escape(labels.get(e, e))}: named in {v["named"]} of {v["runs"]} runs">{escape(labels.get(e, e))} {v["named"]}/{v["runs"]}</span>'
        for e, v in r["engines"].items()
    )
    src = ", ".join(escape(s) for s in r["sources"]) or "—"
    width = max(4, round(100 * r["score"] / max(0.0001, _TOP[0])))
    return (
        f'<li><div class="rank">{i}</div><div class="body"><div class="name">{escape(r["name"])}</div>'
        f'<div class="bar"><span style="width:{width}%"></span></div>'
        f'<div class="chips">{chips}</div><div class="src">sources the engines cited: {src} · best position {r["best_position"]}</div></div></li>'
    )


_TOP: list[float] = [1.0]


def render_query_page(q: Query, ranking: dict[str, Any], cmp: dict[str, Any] | None = None) -> str:
    global _TOP
    results = ranking["results"]
    _TOP = [results[0]["score"]] if results else [1.0]
    rows = "".join(_row(i, r, ranking["engine_labels"]) for i, r in enumerate(results, start=1))
    lang = "he" if q.lang == "he" else "en"
    q_enc = escape(q.text.replace(" ", "+"))
    google_col, gap = render_compare(cmp, f"../search.html?q={q_enc}") if cmp else (NO_GOOGLE, "")
    title = f"{INTENT_LABELS.get(q.intent, q.intent)} · {q.city}: what the AI engines show for “{q.text[:70]}”"
    top = ", ".join(r["name"] for r in results[:3])
    description = (
        f"Asked {ranking['runs']} times across {len(ranking['engines'])} AI engines. Most named: {top}."
        if results
        else "No option named yet."
    )
    engines_txt = ", ".join(
        f"{ranking['engine_labels'][e]} x{n}" for e, n in ranking["engines"].items()
    )
    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": title,
            "dateModified": ranking["last_asked"] or "",
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "numberOfItems": len(results),
            "itemListElement": [
                {"@type": "ListItem", "position": i, "name": r["name"]}
                for i, r in enumerate(results, start=1)
            ],
            "publisher": {"@type": "Organization", "name": "Meerada", "url": "https://meerada.app"},
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    return PAGE.format(
        lang=lang,
        rtl=' dir="rtl"' if lang == "he" else "",
        title=escape(title),
        slug=escape(q.id),
        description=escape(description),
        updated=escape(ranking["last_asked"] or ""),
        jsonld=jsonld,
        h1=escape(q.text),
        lede=f"What ChatGPT, Claude and the other engines answer when people ask this — the options they name, ranked by how consistently and how high they name them. {escape(q.city)} · {escape(INTENT_LABELS.get(q.intent, q.intent))}.",
        meta=f"{ranking['runs']} answers · {escape(engines_txt)} · last asked {escape((ranking['last_asked'] or '')[:10])} · {ranking['distinct']} distinct options named",
        rows=rows or '<li class="none">No answers with named options yet.</li>',
        google_col=google_col,
        gap=gap,
        q_enc=q_enc,
        note='Measured through the models\' APIs with web search; the consumer apps can differ. Options are read from the answer text by a program; the score is Σ engine weight x share of runs naming it x 1/√position. No star ratings, no payment affects this order. Raw answers: <a href="../visibility_state.json">visibility_state.json</a>.',
    )


def build_query_pages(
    state: State,
    out_dir: Path,
    queries: tuple[Query, ...] = QUESTIONS,
    google_dir: Path = DATA_DIR,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    by_query: dict[str, list[Any]] = {}
    for a in state.answers:
        by_query.setdefault(a.query_id, []).append(a)
    index: list[dict[str, Any]] = []
    written: list[Path] = []
    for q in queries:
        answers = by_query.get(q.id, [])
        if not any(not a.error for a in answers):
            continue
        ranking = rank(answers)
        snap = load_snapshot(q.id, google_dir)
        cmp = compare(ranking, snap)
        payload = {
            "id": q.id,
            "text": q.text,
            "city": q.city,
            "country": q.country,
            "lang": q.lang,
            "category": q.category,
            "intent": q.intent,
            **ranking,
            "google": snap.model_dump() if snap else None,
            "comparison": cmp,
        }
        (out_dir / f"{q.id}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        (out_dir / f"{q.id}.html").write_text(render_query_page(q, ranking, cmp), encoding="utf-8")
        written += [out_dir / f"{q.id}.json", out_dir / f"{q.id}.html"]
        index.append(
            {
                "id": q.id,
                "text": q.text,
                "city": q.city,
                "category": q.category,
                "intent": q.intent,
                "lang": q.lang,
                "runs": ranking["runs"],
                "updated": (ranking["last_asked"] or "")[:10],
                "top": [r["name"] for r in ranking["results"][:3]],
            }
        )
    (out_dir / "index.json").write_text(
        json.dumps(
            {"generated_at": datetime.now(tz=UTC).isoformat(), "queries": index}, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    items = "".join(
        f'<li><a href="{escape(i["id"])}.html">{escape(i["text"])}</a> <span class="s">· {escape(i["city"])} · {i["runs"]} answers · top: {escape(", ".join(i["top"]))}</span></li>'
        for i in index
    )
    (out_dir / "index.html").write_text(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>What the AI engines show — every question we measure</title><link rel="canonical" href="https://meerada.app/s/"><link rel="icon" href="../logo.svg" type="image/svg+xml"><script src="../assets/family.js" defer></script><link rel="stylesheet" href="../assets/search.css"></head><body><div class="wrap"><div class="crumb"><a href="../search.html">← Search anything</a></div><h1>Every question we measure</h1><p class="lede">{len(index)} questions, each answered repeatedly by several AI engines. Click one to see who they name.</p><ul class="list">{items}</ul></div></body></html>',
        encoding="utf-8",
    )
    written += [out_dir / "index.json", out_dir / "index.html"]
    return written
