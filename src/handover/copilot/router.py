"""Copilot router — pick the model that clears the quality bar for the least risk.

Reads the same live grade the public board publishes (grade_state.json) and, by
default, restricts the choice to free-tier providers so the Copilot never spends
real money unless the user names a paid model explicitly.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

FREE_PROVIDERS = frozenset({"groq", "openrouter", "ollama"})


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    provider: str
    grade: float
    free: bool


def _provider_of(model_id: str) -> str:
    low = model_id.lower()
    return low.split("/", 1)[0] if "/" in low else "groq"


def pick(
    candidates: list[Candidate],
    *,
    min_grade: float = 0.0,
    prefer_free: bool = True,
) -> Candidate | None:
    """Highest-grade candidate at or above ``min_grade``; free-tier first."""
    pool = [c for c in candidates if c.grade >= min_grade]
    if prefer_free:
        pool = [c for c in pool if c.free] or pool
    return max(pool, key=lambda c: c.grade) if pool else None


def load_candidates(grade_state: Path) -> list[Candidate]:
    """Parse the published grade state into router candidates (defensive)."""
    if not grade_state.exists():
        return []
    try:
        data = json.loads(grade_state.read_text(encoding="utf-8"))
    except ValueError:
        return []
    cards = data.get("cards", {}) if isinstance(data, dict) else {}
    out: list[Candidate] = []
    for model_id, card in cards.items():
        card = card if isinstance(card, dict) else {}
        provider = str(card.get("provider") or "") or _provider_of(str(model_id))
        grade = float(card.get("score") or card.get("grade") or 0.0)
        out.append(
            Candidate(
                model_id=str(model_id),
                provider=provider,
                grade=grade,
                free=provider in FREE_PROVIDERS,
            )
        )
    return out
