"""Editorial guides and profile pages on meerada.app — the outside-in lever the evidence
ranks first (third-party pages that name the business), built the way the engines cite:
one deep page per city x category, a fact table, numbers, a visible update date, sources,
and the disclosure the law asks for. No star ratings, no claims of first-hand experience,
alphabetical order unless the guide states another factual criterion.

Data: ``data/guides/<slug>.json`` → ``site/guides/<slug>.html`` (+ ``guides/index.html``).
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DISCLOSURE = (
    "Published by Meerada, a visibility service. The businesses listed did not pay and were not "
    "consulted; facts come from their own websites and public listings on the dates shown. "
    "Nothing here is a consumer review. Corrections: hello@meerada.app."
)


class Business(BaseModel):
    name: str
    website: str = ""
    phone: str = ""
    address: str = ""
    hours: str = ""
    services: list[str] = Field(default_factory=list)
    areas: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    since: str = ""
    licence: str = ""
    prices: str = ""
    source: str = ""  # where each fact was read (their site / listing), with date in `checked`
    checked: str = ""
    note: str = ""


class Guide(BaseModel):
    slug: str
    city: str
    country: str = ""
    category: str
    title: str
    intro: str
    criteria: list[str] = Field(default_factory=list)  # what the table compares, in words
    order: str = "alphabetical"  # the stated, factual ordering rule
    updated: str
    businesses: list[Business]
    sources: list[str] = Field(default_factory=list)
    lang: str = "en"


def _jsonld(g: Guide) -> str:
    items = []
    for i, b in enumerate(sorted(g.businesses, key=lambda b: b.name.lower()), start=1):
        node: dict[str, Any] = {"@type": "LocalBusiness", "name": b.name}
        if b.website:
            node["url"] = b.website
        if b.phone:
            node["telephone"] = b.phone
        if b.address:
            node["address"] = b.address
        if b.hours:
            node["openingHours"] = b.hours
        items.append({"@type": "ListItem", "position": i, "item": node})
    data = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": g.title,
        "dateModified": g.updated,
        "itemListOrder": "https://schema.org/ItemListUnordered",
        "numberOfItems": len(items),
        "itemListElement": items,
        "publisher": {"@type": "Organization", "name": "Meerada", "url": "https://meerada.app"},
    }
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _row(b: Business) -> str:
    cells = [
        f"<td><b>{escape(b.name)}</b>"
        + (
            f'<div class="s"><a href="{escape(b.website)}" rel="nofollow">{escape(b.website.removeprefix("https://").removeprefix("http://").rstrip("/"))}</a></div>'
            if b.website
            else ""
        )
        + "</td>",
        f"<td>{escape(', '.join(b.services)) or '—'}</td>",
        f"<td>{escape(', '.join(b.areas)) or '—'}</td>",
        f"<td>{escape(b.hours) or '—'}</td>",
        f"<td>{escape(b.prices) or '—'}</td>",
        f"<td>{escape(b.phone) or '—'}</td>",
        f"<td>{escape(b.since) or '—'}{(' · ' + escape(b.licence)) if b.licence else ''}</td>",
        f'<td class="s">{escape(b.checked) or "—"}</td>',
    ]
    return "<tr>" + "".join(cells) + "</tr>"


def render_guide(g: Guide) -> str:
    rtl = ' dir="rtl"' if g.lang == "he" else ""
    rows = "".join(_row(b) for b in sorted(g.businesses, key=lambda b: b.name.lower()))
    criteria = "".join(f"<li>{escape(c)}</li>" for c in g.criteria)
    sources = "".join(
        f'<li><a href="{escape(s)}" rel="nofollow">{escape(s)}</a></li>' for s in g.sources
    )
    notes = "".join(
        f"<p><b>{escape(b.name)}</b> — {escape(b.note)}"
        + (
            f' <span class="s">(source: <a href="{escape(b.source)}" rel="nofollow">{escape(b.source)}</a>, {escape(b.checked)})</span>'
            if b.source
            else ""
        )
        + "</p>"
        for b in sorted(g.businesses, key=lambda b: b.name.lower())
        if b.note
    )
    return f"""<!doctype html><html lang="{escape(g.lang)}"{rtl}><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(g.title)} ({g.updated[:4]})</title>
<link rel="canonical" href="https://meerada.app/guides/{escape(g.slug)}.html">
<link rel="icon" href="../logo.svg" type="image/svg+xml">
<meta name="description" content="{escape(g.intro[:155])}">
<meta property="og:title" content="{escape(g.title)}"><meta property="og:description" content="{escape(g.intro[:200])}"><meta property="og:type" content="article">
<meta property="article:modified_time" content="{escape(g.updated)}">
<script type="application/ld+json">{_jsonld(g)}</script>
<script src="../assets/family.js" defer></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
  :root{{--panel:#F7F9FC;--line:#DDE4EE;--text:#0F172A;--muted:#5B6B82;--teal:#0E8A7E}}
  body{{margin:0;color:var(--text);font-family:"IBM Plex Sans",system-ui,sans-serif;line-height:1.55}} .wrap{{max-width:1040px;margin:0 auto;padding:0 1.1rem}}
  h1{{font-family:Archivo,system-ui;font-weight:900;font-size:clamp(1.6rem,4vw,2.4rem);margin:2rem 0 .3rem}} .lede{{color:var(--muted);font-size:1.02rem}}
  .meta{{font-family:"IBM Plex Mono",monospace;font-size:.74rem;color:var(--muted);margin:.4rem 0 1.2rem}}
  table{{width:100%;border-collapse:collapse;font-size:.86rem}} th,td{{text-align:left;padding:.5rem .55rem;border-bottom:1px solid var(--line);vertical-align:top}} th{{font-family:"IBM Plex Mono",monospace;font-size:.68rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
  .s{{color:var(--muted);font-size:.76rem}} .box{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.8rem 1rem;margin:1rem 0;font-size:.86rem}}
  h2{{font-family:Archivo,system-ui;font-size:1.15rem;margin:1.6rem 0 .5rem}} [dir=rtl] th,[dir=rtl] td{{text-align:right}}
</style></head><body><div class="wrap">
<h1>{escape(g.title)}</h1>
<p class="lede">{escape(g.intro)}</p>
<div class="meta">Updated {escape(g.updated)} · {len(g.businesses)} businesses · order: {escape(g.order)} · {escape(g.city)}{(", " + escape(g.country)) if g.country else ""}</div>
<div class="box">{escape(DISCLOSURE)}</div>
<h2>What this guide compares</h2><ul>{criteria}</ul>
<h2>The businesses, side by side</h2>
<table><thead><tr><th>Business</th><th>Services</th><th>Areas</th><th>Hours</th><th>Prices</th><th>Phone</th><th>Since · licence</th><th>Checked</th></tr></thead><tbody>{rows}</tbody></table>
{("<h2>Notes</h2>" + notes) if notes else ""}
{('<h2>Sources</h2><ul class="s">' + sources + "</ul>") if sources else ""}
<p class="s">Every fact above was read from the business's own website or a public listing on the date in the "Checked" column. If you run one of these businesses and something is wrong, write to hello@meerada.app and we correct it within a week.</p>
</div></body></html>
"""


def render_index(guides: list[Guide]) -> str:
    items = "".join(
        f'<li><a href="{escape(g.slug)}.html">{escape(g.title)}</a> <span class="s">· {escape(g.city)} · updated {escape(g.updated)}</span></li>'
        for g in sorted(guides, key=lambda g: (g.city, g.category))
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meerada guides — businesses compared by the facts</title><link rel="canonical" href="https://meerada.app/guides/">
<link rel="icon" href="../logo.svg" type="image/svg+xml"><script src="../assets/family.js" defer></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>body{{margin:0;font-family:"IBM Plex Sans",system-ui,sans-serif;color:#0F172A;line-height:1.55}} .wrap{{max-width:860px;margin:0 auto;padding:2rem 1.1rem}} .s{{color:#5B6B82;font-size:.8rem}} li{{margin:.4rem 0}}</style></head>
<body><div class="wrap"><h1>Guides</h1><p class="s">{escape(DISCLOSURE)}</p><ul>{items}</ul></div></body></html>
"""


def load_guides(data_dir: Path) -> list[Guide]:
    return [
        Guide.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(data_dir.glob("*.json"))
    ]


def build_guides(data_dir: Path, out_dir: Path) -> list[Path]:
    guides = load_guides(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for g in guides:
        path = out_dir / f"{g.slug}.html"
        path.write_text(render_guide(g), encoding="utf-8")
        written.append(path)
    if guides:
        index = out_dir / "index.html"
        index.write_text(render_index(guides), encoding="utf-8")
        written.append(index)
    return written
