"""Factual profile pages in the Meerada index — one page per business, built only from
facts read on the business's own site or its public listing, each with a source and a
check date. No ratings, no review quotes, a disclosure line, a correction channel.
JSON-LD LocalBusiness so engines that read structured data can, without us claiming it
moves anything (the evidence says it does not; the mention and the page do).

Data: ``data/profiles/*.json`` ({"profiles": [...]}) → ``site/b/<slug>.html`` + ``site/b/index.html``.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from handover.visibility.guides import DISCLOSURE


class Profile(BaseModel):
    id: str
    name: str
    slug: str
    city: str
    country: str = ""
    category: str
    website: str = ""
    phone: str = ""
    address: str = ""
    hours: str = ""
    summary: str = ""
    services: list[str] = Field(default_factory=list)
    prices: str = ""
    booking: str = ""
    people: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    since: str = ""
    extras: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    checked: str
    discrepancies: str = ""


def _jsonld(p: Profile) -> str:
    node: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": p.name,
        "description": p.summary,
        "address": p.address or p.city,
        "areaServed": p.city,
        "dateModified": p.checked,
        "mainEntityOfPage": f"https://meerada.app/b/{p.slug}.html",
    }
    if p.website:
        node["url"] = p.website
    if p.phone:
        node["telephone"] = p.phone
    if p.hours:
        node["openingHours"] = p.hours
    if p.since:
        node["foundingDate"] = p.since
    if p.services:
        node["knowsAbout"] = p.services
    return json.dumps(node, ensure_ascii=False).replace("</", "<\\/")


def _li(items: list[str]) -> str:
    return "".join(f"<li>{escape(i)}</li>" for i in items)


def _row(label: str, value: str) -> str:
    return f"<tr><th>{escape(label)}</th><td>{escape(value)}</td></tr>" if value else ""


def render_profile(p: Profile) -> str:
    site = p.website.removeprefix("https://").removeprefix("http://").rstrip("/")
    rows = (
        _row("What", ", ".join(p.services))
        + _row("Address", p.address)
        + _row("Hours", p.hours)
        + _row("Phone", p.phone)
        + _row("Prices", p.prices)
        + _row("Booking", p.booking)
        + _row("Languages", ", ".join(p.languages))
        + _row("Since", p.since)
        + _row("People", "; ".join(p.people))
        + _row("Also stated", "; ".join(p.extras))
    )
    sources = "".join(
        f'<li><a href="{escape(s)}" rel="nofollow">{escape(s)}</a></li>' for s in p.sources
    )
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(p.name)} — {escape(p.category)} in {escape(p.city)}</title>
<link rel="canonical" href="https://meerada.app/b/{escape(p.slug)}.html">
<link rel="icon" href="../logo.svg" type="image/svg+xml">
<meta name="description" content="{escape(p.summary[:155])}">
<meta property="og:title" content="{escape(p.name)} — {escape(p.category)} in {escape(p.city)}"><meta property="og:description" content="{escape(p.summary[:200])}"><meta property="og:type" content="profile">
<meta property="article:modified_time" content="{escape(p.checked)}">
<script type="application/ld+json">{_jsonld(p)}</script>
<script src="../assets/family.js" defer></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap">
<style>
  :root{{--panel:#F7F9FC;--line:#DDE4EE;--text:#0F172A;--muted:#5B6B82;--teal:#0E8A7E}}
  body{{margin:0;color:var(--text);font-family:"IBM Plex Sans",system-ui,sans-serif;line-height:1.55}} .wrap{{max-width:860px;margin:0 auto;padding:0 1.1rem}}
  h1{{font-family:Archivo,system-ui;font-weight:900;font-size:clamp(1.6rem,4vw,2.4rem);margin:2rem 0 .2rem}} .sub{{color:var(--muted);font-size:1rem}}
  .meta{{font-family:"IBM Plex Mono",monospace;font-size:.74rem;color:var(--muted);margin:.4rem 0 1.2rem}}
  table{{width:100%;border-collapse:collapse;font-size:.92rem;margin:1rem 0}} th,td{{text-align:left;padding:.5rem .55rem;border-bottom:1px solid var(--line);vertical-align:top}} th{{width:9rem;font-family:"IBM Plex Mono",monospace;font-size:.7rem;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}}
  .box{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:.8rem 1rem;margin:1rem 0;font-size:.86rem}} .s{{color:var(--muted);font-size:.78rem}}
  h2{{font-family:Archivo,system-ui;font-size:1.1rem;margin:1.4rem 0 .4rem}}
</style></head><body><div class="wrap">
<h1>{escape(p.name)}</h1>
<div class="sub">{escape(p.category)} · {escape(p.city)}{(", " + escape(p.country)) if p.country else ""}{(' · <a href="' + escape(p.website) + '" rel="nofollow">' + escape(site) + "</a>") if p.website else ""}</div>
<div class="meta">Facts checked {escape(p.checked)} · sources below · <a href="index.html">all profiles</a></div>
<p>{escape(p.summary)}</p>
<table>{rows}</table>
{('<div class="s">Discrepancy noted: ' + escape(p.discrepancies) + "</div>") if p.discrepancies else ""}
<div class="box">{escape(DISCLOSURE)}</div>
<h2>Sources</h2><ul class="s">{sources}</ul>
<p class="s">Run this business? Corrections and additions: hello@meerada.app — we update within a week and show the date.</p>
</div></body></html>
"""


def render_profile_index(profiles: list[Profile]) -> str:
    items = "".join(
        f'<li><a href="{escape(p.slug)}.html">{escape(p.name)}</a> <span class="s">· {escape(p.category)} · {escape(p.city)} · checked {escape(p.checked)}</span></li>'
        for p in sorted(profiles, key=lambda p: (p.city, p.name.lower()))
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meerada index — business profiles, facts only</title><link rel="canonical" href="https://meerada.app/b/">
<link rel="icon" href="../logo.svg" type="image/svg+xml"><script src="../assets/family.js" defer></script>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>body{{margin:0;font-family:"IBM Plex Sans",system-ui,sans-serif;color:#0F172A;line-height:1.55}} .wrap{{max-width:860px;margin:0 auto;padding:2rem 1.1rem}} .s{{color:#5B6B82;font-size:.8rem}} li{{margin:.4rem 0}}</style></head>
<body><div class="wrap"><h1>Business profiles</h1><p class="s">{escape(DISCLOSURE)}</p><ul>{items}</ul></div></body></html>
"""


def load_profiles(data_dir: Path) -> list[Profile]:
    out: list[Profile] = []
    for path in sorted(data_dir.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        out += [Profile.model_validate(p) for p in raw.get("profiles", [])]
    return out


def build_profiles(data_dir: Path, out_dir: Path) -> list[Path]:
    profiles = load_profiles(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for p in profiles:
        path = out_dir / f"{p.slug}.html"
        path.write_text(render_profile(p), encoding="utf-8")
        written.append(path)
    if profiles:
        index = out_dir / "index.html"
        index.write_text(render_profile_index(profiles), encoding="utf-8")
        written.append(index)
    return written
