"""Controlled experiments: a business, one lever, the questions it should appear in,
a start date. The registry is ``data/experiments.json`` (hand-edited); the report
tracks, per engine, whether the business was *named* (an alias among the extracted
names) or merely *cited* (its own domain among the citations) in each answer to its
questions, before and after the start — the only honest way to learn which lever
moves an engine. ``control: true`` marks a business that gets no lever.

    {"experiments": [{"id": "shai-gbp", "business": "Shai Plumbing Services",
      "aliases": ["Shai Plumbing"], "domain": "shai-plumb.co.il",
      "queries": ["tlv-plumber", "hfa-plumber-he"], "lever": "guide",
      "started": "2026-12-01", "city": "Tel Aviv", "category": "plumber", "notes": "…"}]}
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from handover.visibility.extract import normalize
from handover.visibility.state import Answer, State

LEVERS: tuple[str, ...] = (
    "guide",  # an editorial comparison guide on meerada.app that includes the business
    "profile",  # a factual profile page in the Meerada index (JSON-LD, correction channel)
    "outreach",  # a truthful mention earned on an existing third-party page
    "directory",  # Yelp / Tripadvisor / open directory listing created from public facts
    "google-business-profile",  # owner-side: claim/fix GBP (phase 2 only)
    "own-site",  # owner-side: answer pages on their site (phase 2 only)
    "none",  # control
)


class Experiment(BaseModel):
    id: str
    business: str
    aliases: list[str] = Field(default_factory=list)
    domain: str = ""
    queries: list[str]
    lever: str = "none"
    started: date
    city: str = ""
    category: str = ""
    control: bool = False
    notes: str = ""

    def keys(self) -> set[str]:
        return {normalize(n) for n in [self.business, *self.aliases] if normalize(n)}


def load_experiments(path: Path) -> list[Experiment]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return [Experiment.model_validate(e) for e in raw.get("experiments", [])]


def named_in(keys: set[str], name_keys: list[str]) -> bool:
    return any(k == nk or k in nk or nk in k for k in keys for nk in name_keys if nk)


def cited_in(domain: str, citations: list[str]) -> bool:
    host = domain.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    host = host.split("/")[0]
    if not host:
        return False
    for c in citations:
        h = urlparse(c if "://" in c else f"https://{c}").netloc.lower().removeprefix("www.")
        if h == host or h.endswith("." + host):
            return True
    return False


def _bucket(exp: Experiment, answers: list[Answer]) -> dict[str, int]:
    keys = exp.keys()
    return {
        "n": len(answers),
        "named": sum(named_in(keys, a.name_keys) for a in answers),
        "cited": sum(cited_in(exp.domain, a.citations) for a in answers),
    }


def track(experiments: list[Experiment], state: State, engines: list[str]) -> list[dict[str, Any]]:
    """Per experiment and engine: answers before/after the start, how many named or cited it,
    and the run-by-run series (newest 60) for the public test-case page."""
    rows: list[dict[str, Any]] = []
    for exp in experiments:
        keys = exp.keys()
        start = datetime(exp.started.year, exp.started.month, exp.started.day, tzinfo=UTC)
        per_engine: dict[str, Any] = {}
        for engine in engines:
            answers = sorted(
                (
                    a
                    for a in state.answers
                    if a.engine == engine and a.query_id in exp.queries and not a.error
                ),
                key=lambda a: a.asked_at,
            )
            before = [a for a in answers if a.asked_at < start]
            after = [a for a in answers if a.asked_at >= start]
            per_engine[engine] = {
                "before": _bucket(exp, before),
                "after": _bucket(exp, after),
                "series": [
                    {
                        "t": a.asked_at.isoformat(),
                        "q": a.query_id,
                        "named": named_in(keys, a.name_keys),
                        "cited": cited_in(exp.domain, a.citations),
                        "names": a.names[:8],
                    }
                    for a in answers
                ][-60:],
            }
        rows.append(
            {
                "id": exp.id,
                "business": exp.business,
                "domain": exp.domain,
                "lever": exp.lever,
                "control": exp.control,
                "started": exp.started.isoformat(),
                "city": exp.city,
                "category": exp.category,
                "queries": exp.queries,
                "notes": exp.notes,
                "engines": per_engine,
            }
        )
    return rows
