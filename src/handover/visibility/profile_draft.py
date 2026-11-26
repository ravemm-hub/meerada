"""A profile draft from a business website — the entity-page lever, started by a program.

Reads the public page once and fills what it can find (name, phone, e-mail, social
links, headings as service candidates, an hours line, an address line, language); every
field is listed under ``_confirm`` because a program's reading is a draft, not a fact.
A person confirms, moves the file from ``drafts/`` to ``data/profiles/``, and the page is
built as usual. Nothing here is published on its own.

    meerada visibility profile-draft https://example.co.il --name "X" --city "Tel Aviv" --category plumber
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from typing import Any

from handover.visibility.audit import Fetch, http_get

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_DESC = re.compile(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{10,400})', re.I)
_H = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_LANG = re.compile(r"<html[^>]*\blang=[\"']([a-zA-Z-]+)", re.I)
_PHONE = re.compile(
    r"(?:\+972|0)(?:[23489]|5\d|7\d)[\s-]?\d{3}[\s-]?\d{4}|\+?\d{1,3}[\s-]?\(?\d{2,4}\)?[\s-]?\d{3,4}[\s-]?\d{3,4}"
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SOCIAL = re.compile(
    r"https?://(?:www\.)?(?:instagram\.com|facebook\.com|tiktok\.com|youtube\.com|wa\.me)/[^\s\"'<>]+",
    re.I,
)
_HOURS = re.compile(
    r"[^.\n]{0,60}(?:open|hours|opening|שעות|פתוח|Sun|Mon|Tue|Wed|Thu|Fri|Sat|א'|ב'-|א-ה)[^.\n]{0,100}",
    re.I,
)
_ADDRESS = re.compile(
    r"[^.\n]{0,40}(?:\bSt\.?\b|\bStreet\b|\bRd\.?\b|\bRoad\b|\bAve\.?\b|\bBlvd\b|רחוב|רח'|שד'|שדרות|דרך)[^.\n]{0,80}",
    re.I,
)
_WS = re.compile(r"\s+")
_SLUG = re.compile(r"[^a-z0-9]+")


def _clean(s: str) -> str:
    return _WS.sub(" ", unescape(_TAG.sub(" ", s))).strip()


def slugify(name: str, city: str) -> str:
    base = _SLUG.sub("-", f"{name} {city}".lower()).strip("-")
    return base or "business"


def draft_profile(
    url: str, name: str = "", city: str = "", category: str = "", fetch: Fetch = http_get
) -> dict[str, Any]:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    status, _headers, html = fetch(url)
    text = _clean(html)
    mt, md = _TITLE.search(html), _DESC.search(html)
    title = _clean(mt.group(1)) if mt else ""
    desc = _clean(md.group(1)) if md else ""
    heads = []
    for h in _H.findall(html):
        t = _clean(h)
        if 3 <= len(t) <= 60 and t not in heads:
            heads.append(t)
    phones = list(dict.fromkeys(m.group(0).strip() for m in _PHONE.finditer(text)))[:2]
    emails = list(dict.fromkeys(m.group(0).rstrip(".") for m in _EMAIL.finditer(html)))[:2]
    socials = list(dict.fromkeys(m.group(0).rstrip("/") for m in _SOCIAL.finditer(html)))[:6]
    hours = _HOURS.search(text)
    address = _ADDRESS.search(text)
    lang = _LANG.search(html)
    name = name or title.split("|")[0].split(" - ")[0].strip()
    today = datetime.now(tz=UTC).date().isoformat()
    profile: dict[str, Any] = {
        "id": slugify(name, city),
        "name": name,
        "slug": slugify(name, city),
        "city": city,
        "country": "",
        "category": category,
        "website": url,
        "phone": phones[0] if phones else "",
        "address": address.group(0).strip() if address else "",
        "hours": hours.group(0).strip() if hours else "",
        "summary": desc,
        "services": heads[:8],
        "prices": "",
        "booking": "",
        "people": [],
        "languages": [lang.group(1).split("-")[0]] if lang else [],
        "since": "",
        "extras": ([f"e-mail: {emails[0]}"] if emails else []) + [f"social: {s}" for s in socials],
        "sources": [url],
        "checked": today,
        "discrepancies": "",
        "_status": status,
        "_confirm": [
            "name",
            "phone",
            "address",
            "hours",
            "summary",
            "services",
            "prices",
            "booking",
            "languages",
            "since",
            "country",
            "people — only business-level facts, never private individuals",
        ],
        "_note": "DRAFT read by a program from the page above on "
        + today
        + ". Confirm every field against the site and the Google listing, remove what is not stated, then move the file to data/profiles/.",
    }
    return profile


def write_draft(profile: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{profile['slug']}.json"
    path.write_text(
        json.dumps({"profiles": [profile]}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
