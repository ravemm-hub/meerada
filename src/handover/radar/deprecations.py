"""Deprecation radar — the lead-generation engine.

Every forced model retirement is an inbound trigger: "the model you use
retires in N days; here is the measured gap to the replacements." This module
loads known retirements, computes urgency from a reference date (injected, so
it is deterministic and testable), and pairs each retiring model with
replacement candidates — enriched with the measured Meerada Grade delta when
index data is available.

Pure metadata: model ids and dates only, no tenant content.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

Status = Literal["active", "deprecated", "retired"]
Urgency = Literal["retired", "critical", "soon", "watch", "clear"]

CRITICAL_DAYS = 30
SOON_DAYS = 90


class Deprecation(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model_id: str
    retires_on: date
    status: Status
    replacements: tuple[str, ...] = ()
    notes: str = ""


class ReplacementOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    grade: float | None = None  # measured Meerada Grade, when index data exists
    grade_delta: float | None = None  # vs the retiring model's grade, if known


class RadarEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model_id: str
    retires_on: date
    days_left: int  # negative once past
    urgency: Urgency
    replacements: tuple[ReplacementOption, ...]
    notes: str


def load_deprecations(path: Path) -> list[Deprecation]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Deprecation.model_validate(d) for d in payload["deprecations"]]


def _urgency(days_left: int, status: Status) -> Urgency:
    if status == "retired" or days_left < 0:
        return "retired"
    if days_left <= CRITICAL_DAYS:
        return "critical"
    if days_left <= SOON_DAYS:
        return "soon"
    if days_left <= 180:
        return "watch"
    return "clear"


def build_radar(
    deprecations: Sequence[Deprecation],
    today: date,
    *,
    grades: Mapping[str, float] | None = None,
) -> list[RadarEntry]:
    """Rank retirements by urgency (soonest first). ``grades`` maps model_id to
    a Meerada Grade so replacements can be shown with a measured delta."""
    grades = grades or {}
    entries: list[RadarEntry] = []
    for dep in deprecations:
        days_left = (dep.retires_on - today).days
        incumbent_grade = grades.get(dep.model_id)
        options = tuple(
            ReplacementOption(
                model_id=rep,
                grade=grades.get(rep),
                grade_delta=(
                    round(grades[rep] - incumbent_grade, 1)
                    if rep in grades and incumbent_grade is not None
                    else None
                ),
            )
            for rep in dep.replacements
        )
        entries.append(
            RadarEntry(
                provider=dep.provider,
                model_id=dep.model_id,
                retires_on=dep.retires_on,
                days_left=days_left,
                urgency=_urgency(days_left, dep.status),
                replacements=options,
                notes=dep.notes,
            )
        )
    # Actionable first: not-yet-retired sorted by soonest; retired last.
    order = {"critical": 0, "soon": 1, "watch": 2, "clear": 3, "retired": 4}
    entries.sort(key=lambda e: (order[e.urgency], e.days_left))
    return entries


def actionable(entries: Sequence[RadarEntry]) -> list[RadarEntry]:
    """Entries worth a migration conversation now (retiring within 90 days)."""
    return [e for e in entries if e.urgency in ("critical", "soon")]
