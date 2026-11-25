"""Why was this option shown? Features read from the answer itself — evidence ``derived``,
no external lookups. Per answer: how many candidates, whether the engine crowned one,
whether it quoted ratings or prices, how many citations are "best of" guides, and how
many named options had their own site cited. Aggregated per engine and intent, these
are the first observable regularities of each engine's choosing.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from urllib.parse import urlparse

from handover.visibility.extract import normalize

_PICK = re.compile(
    r"top pick|my pick|best overall|overall best|if i had to (pick|choose)"
    r"|i['\u2019]d (start|go) with"
    r"|my (first|top) recommendation|the standout|stands out",
    re.I,
)
_RATING = re.compile(r"\b[1-5]\.\d\b|★|⭐|\bstars?\b", re.I)
_PRICE = re.compile(r"[$£€₪]\s?\d|\d+\s?(?:USD|GBP|EUR|ILS|NIS|shekels?|₪)\b|\bfrom \d+\b", re.I)
_LISTICLE = re.compile(r"best|top-?\d+|top\b|guide|review|ranking|ranked|vs\b|compar", re.I)
_TABLE = re.compile(r"^\s*\|.*\|\s*$", re.M)
_STOP_TOKENS = {
    "the", "and", "for", "studio", "clinic", "dental", "law", "firm", "office", "center",
    "centre", "ltd", "inc", "llc", "co", "company", "group", "services", "service", "shop",
    "store", "hotel", "london", "york", "aviv", "tel", "new", "city", "israel", "uk", "usa",
}  # fmt: skip

Features = dict[str, float]
SEGMENT_MAX = 400


def _segments(text: str, names: Sequence[str]) -> Iterator[tuple[str, str]]:
    """The slice of the answer that belongs to each named option: from its first
    mention to the next option's (or at most SEGMENT_MAX chars)."""
    low = text.lower()
    found = sorted((low.find(n.lower()), n) for n in names if low.find(n.lower()) >= 0)
    for i, (pos, name) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else min(len(text), pos + SEGMENT_MAX)
        yield name, text[pos : max(end, pos + len(name))]


def _hosts(citations: Sequence[str]) -> list[str]:
    hosts: list[str] = []
    for c in citations:
        host = urlparse(c if "://" in c else f"https://{c}").netloc.lower().removeprefix("www.")
        hosts.append(host or c.lower())
    return hosts


def _own_site(name: str, hosts: Sequence[str]) -> bool:
    tokens = [t for t in normalize(name).split() if len(t) >= 4 and t not in _STOP_TOKENS]
    if not tokens:
        return False
    for host in hosts:
        if "google." in host or "maps" in host:
            continue
        flat = re.sub(r"[^a-z0-9]", "", host.split(".")[0] if host.count(".") <= 2 else host)
        if any(t in flat for t in tokens):
            return True
    return False


def answer_features(text: str, citations: Sequence[str], names: Sequence[str]) -> Features:
    hosts = _hosts(citations)
    segments = list(_segments(text, names))
    rated = sum(1 for _, seg in segments if _RATING.search(seg))
    priced = sum(1 for _, seg in segments if _PRICE.search(seg))
    own = sum(1 for nm in names if _own_site(nm, hosts))
    listicle = sum(1 for c in citations if _LISTICLE.search(urlparse(c).path or c))
    return {
        "candidates": float(len(names)),
        "has_pick": float(bool(_PICK.search(text))),
        "has_table": float(len(_TABLE.findall(text)) >= 3),
        "rated": float(rated),
        "priced": float(priced),
        "own_site": float(own),
        "cites": float(len(citations)),
        "listicle_cites": float(listicle),
        "distinct_hosts": float(len(set(hosts))),
        "chars": float(len(text)),
    }


def jaccard(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Overlap of two name-key sets; None when both are empty (nothing to compare)."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return None
    return len(sa & sb) / len(sa | sb)
