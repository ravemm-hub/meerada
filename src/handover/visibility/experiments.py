"""Controlled experiments: a business, one lever, the questions it should appear in,
a start date. The registry is ``data/experiments.json`` (hand-edited); the report
tracks, per engine, whether any alias of the business was named in each answer to
its questions, before and after the start — the only honest way to learn which
lever moves an engine.

    {"experiments": [{"id": "shai-gbp", "business": "Shai Plumbing Services",
      "aliases": ["Shai Plumbing"], "queries": ["tlv-plumber", "hfa-plumber-he"],
      "lever": "google-business-profile", "started": "2026-12-01", "notes": "…"}]}
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from handover.visibility.extract import normalize
from handover.visibility.state import State

LEVERS: tuple[str, ...] = (
    "google-business-profile",  # claim/fix GBP: category, hours, photos, reviews
    "listicle",  # get into a "best X in Y" article the engines cite
    "own-site",  # a crawlable page with the service, area, FAQ, JSON-LD
    "directory",  # Yelp / Tripadvisor / local directory listing
    "reviews",  # review volume and recency
    "none",  # control
)


class Experiment(BaseModel):
    id: str
    business: str
    aliases: list[str] = Field(default_factory=list)
    queries: list[str]
    lever: str = "none"
    started: date
    notes: str = ""

    def keys(self) -> set[str]:
        return {normalize(n) for n in [self.business, *self.aliases] if normalize(n)}


def load_experiments(path: Path) -> list[Experiment]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    return [Experiment.model_validate(e) for e in raw.get("experiments", [])]


def _present(keys: set[str], name_keys: list[str]) -> bool:
    return any(k == nk or k in nk or nk in k for k in keys for nk in name_keys if nk)


def track(experiments: list[Experiment], state: State, engines: list[str]) -> list[dict[str, Any]]:
    """Per experiment and engine: answers before/after the start and how many named it."""
    rows: list[dict[str, Any]] = []
    for exp in experiments:
        keys = exp.keys()
        start = datetime(exp.started.year, exp.started.month, exp.started.day, tzinfo=UTC)
        per_engine: dict[str, Any] = {}
        for engine in engines:
            answers = [
                a
                for a in state.answers
                if a.engine == engine and a.query_id in exp.queries and not a.error
            ]
            before = [a for a in answers if a.asked_at < start]
            after = [a for a in answers if a.asked_at >= start]
            per_engine[engine] = {
                "before": {
                    "n": len(before),
                    "present": sum(_present(keys, a.name_keys) for a in before),
                },
                "after": {
                    "n": len(after),
                    "present": sum(_present(keys, a.name_keys) for a in after),
                },
                "series": [
                    {
                        "t": a.asked_at.isoformat(),
                        "q": a.query_id,
                        "present": _present(keys, a.name_keys),
                    }
                    for a in sorted(answers, key=lambda a: a.asked_at)
                ][-30:],
            }
        rows.append(
            {
                "id": exp.id,
                "business": exp.business,
                "lever": exp.lever,
                "started": exp.started.isoformat(),
                "queries": exp.queries,
                "notes": exp.notes,
                "engines": per_engine,
            }
        )
    return rows
