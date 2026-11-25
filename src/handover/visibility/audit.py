"""Entity audit v0: what a business's own site and robots say about its chances with the
AI engines. Heuristic, evidence ``declared`` — a checklist until the Search Lab has enough
answers to calibrate a real model. No external APIs: the site, its robots.txt, and our own
stored answers.

    meerada visibility audit https://example.co.il --name "Example Plumbing"
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse

Fetch = Callable[[str], tuple[int, dict[str, str], str]]

SEARCH_BOTS = ("OAI-SearchBot", "PerplexityBot", "Claude-SearchBot", "Googlebot", "Bingbot")
TRAINING_BOTS = ("GPTBot", "ClaudeBot", "Google-Extended")
SOCIAL = ("instagram.com", "facebook.com", "tiktok.com", "youtube.com", "linkedin.com", "x.com")

_TAG = re.compile(r"<script.*?</script>|<style.*?</style>|<[^>]+>", re.S | re.I)
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?\(?0?\d{1,3}\)?[\s-]?\d{3}[\s-]?\d{4}")
_HOURS = re.compile(r"\b(hours|open(ing)?|mon|sun|שעות|פתוח|ראשון|א'-ה')\b", re.I)
_PRICE = re.compile(r"[$£€₪]\s?\d|\d+\s?(?:USD|GBP|EUR|ILS|NIS|ש\"ח|שקל)", re.I)
_ADDRESS = re.compile(r"\b(street|st\.|road|rd\.|avenue|ave\.|רחוב|רח'|שדרות|דרך)\b", re.I)
_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\']', re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
_LANG = re.compile(r"<html[^>]*\blang=[\"']([a-zA-Z-]+)", re.I)
_DATE = re.compile(r"\b(20[12]\d)[-/.](0?[1-9]|1[0-2])\b|\b(20[12]\d)\b")


def http_get(url: str) -> tuple[int, dict[str, str], str]:
    """Live fetch (not exercised by tests): status, lower-cased headers, body text."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "MeeradaAudit/0.1 (+https://meerada.app)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(600_000).decode("utf-8", errors="replace")
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body
    except urllib.error.HTTPError as exc:
        return exc.code, {}, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}, ""


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    weight: int
    detail: str = ""
    fix: str = ""


@dataclass
class Audit:
    url: str
    name: str
    status: int
    checks: list[Check] = field(default_factory=list)

    @property
    def score(self) -> int:
        total = sum(c.weight for c in self.checks)
        got = sum(c.weight for c in self.checks if c.ok)
        return round(100 * got / total) if total else 0

    def fixes(self) -> list[str]:
        return [c.fix for c in sorted(self.checks, key=lambda c: -c.weight) if not c.ok and c.fix]

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "name": self.name,
            "status": self.status,
            "score": self.score,
            "grade": "declared",
            "checks": [c.__dict__ for c in self.checks],
            "fixes": self.fixes(),
        }


def robots_blocks(robots: str, bots: tuple[str, ...]) -> dict[str, bool]:
    """True when a bot (or *) group has ``Disallow: /``. A small, forgiving parser."""
    groups: dict[str, list[str]] = {}
    current: list[str] = []
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            current = groups.setdefault(value.lower(), [])
        elif key == "disallow" and current is not None:
            current.append(value)
    out: dict[str, bool] = {}
    for bot in bots:
        rules = groups.get(bot.lower())
        if rules is None:
            rules = groups.get("*", [])
        out[bot] = "/" in rules
    return out


def audit(url: str, name: str = "", fetch: Fetch = http_get) -> Audit:
    if "://" not in url:
        url = "https://" + url
    status, _headers, html = fetch(url)
    text = unescape(_TAG.sub(" ", html))
    text = re.sub(r"\s+", " ", text).strip()
    words = len(text.split())
    result = Audit(url=url, name=name, status=status)
    add = result.checks.append

    add(
        Check(
            "reachable",
            "Site reachable",
            200 <= status < 400,
            10,
            f"HTTP {status}",
            "Fix the site: the engines cannot cite a page they cannot fetch.",
        )
    )
    _, _, robots = fetch(urljoin(url, "/robots.txt"))
    blocks = robots_blocks(robots or "", SEARCH_BOTS)
    blocked = [b for b, v in blocks.items() if v]
    add(
        Check(
            "search_bots",
            "Search bots allowed (OAI-SearchBot, PerplexityBot, Claude-SearchBot, Googlebot)",
            not blocked,
            10,
            "blocked: " + ", ".join(blocked) if blocked else "all allowed",
            "Unblock the search crawlers in robots.txt — blocked sites are absent from AI answers.",
        )
    )
    add(
        Check(
            "text",
            "Enough extractable text (≥300 words)",
            words >= 300,
            8,
            f"{words} words",
            "Put the service, area, prices and FAQ as real text on the page, "
            "not only images or scripts.",
        )
    )
    title = _TITLE.search(html)
    add(
        Check(
            "title",
            "Descriptive title with the service and the city",
            bool(title and len(title.group(1).strip()) > 12),
            4,
            (title.group(1).strip()[:80] if title else "none"),
            "Give the page a title like 'Plumber in Tel Aviv — <name>'.",
        )
    )
    add(
        Check(
            "h1",
            "One clear H1",
            len(_H1.findall(html)) == 1,
            2,
            f"{len(_H1.findall(html))} h1",
            "Use exactly one H1 that says what you do and where.",
        )
    )
    add(
        Check(
            "phone",
            "Phone number on the page",
            bool(_PHONE.search(text)),
            6,
            "",
            "Show the phone number as text (engines match it with your listings).",
        )
    )
    add(
        Check(
            "address",
            "Address on the page",
            bool(_ADDRESS.search(text)),
            6,
            "",
            "Show the street address as text; it must match Google and Yelp exactly.",
        )
    )
    add(
        Check(
            "hours",
            "Opening hours on the page",
            bool(_HOURS.search(text)),
            4,
            "",
            "Show opening hours as text.",
        )
    )
    add(
        Check(
            "prices",
            "Prices or price ranges",
            bool(_PRICE.search(text)),
            5,
            "",
            "Show prices or ranges: engines quote numbers and prefer pages that have them.",
        )
    )
    socials = sorted({s for s in SOCIAL if s in html.lower()})
    add(
        Check(
            "social",
            "Links to social profiles (Instagram, Facebook, TikTok, YouTube)",
            len(socials) >= 2,
            5,
            ", ".join(socials) or "none",
            "Link your Instagram/Facebook/TikTok/YouTube from the site.",
        )
    )
    add(
        Check(
            "fresh",
            "A recent year or date on the page",
            bool(_DATE.search(text)),
            4,
            "",
            "Show when the page was last updated; stale pages are filtered.",
        )
    )
    add(Check("lang", "Language declared", bool(_LANG.search(html)), 1, "", "Set <html lang>."))
    add(
        Check(
            "jsonld",
            "Structured data present (informational: no measured effect on AI citations)",
            bool(_JSONLD.search(html)),
            0,
            "",
            "",
        )
    )
    sitemap_status, _, _ = fetch(urljoin(url, "/sitemap.xml"))
    add(
        Check(
            "sitemap",
            "sitemap.xml",
            200 <= sitemap_status < 400,
            2,
            f"HTTP {sitemap_status}",
            "Publish a sitemap.xml and submit it to Bing (IndexNow) and Google.",
        )
    )
    host = urlparse(url).netloc
    add(
        Check(
            "name_match",
            "Business name appears in the page",
            bool(name) and name.lower() in text.lower(),
            3,
            host,
            "Write the business name exactly as it appears on Google and Yelp.",
        )
    )
    return result


def format_audit(a: Audit) -> str:
    lines = [f"{a.name or a.url} — score {a.score}/100 (declared, heuristic v0)"]
    for c in a.checks:
        mark = "ok " if c.ok else "-- "
        lines.append(f"  {mark}{c.label}" + (f"  [{c.detail}]" if c.detail else ""))
    if a.fixes():
        lines.append("fixes, in order:")
        lines += [f"  {i + 1}. {f}" for i, f in enumerate(a.fixes())]
    return "\n".join(lines)
