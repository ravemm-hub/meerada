"""The continuous grading orchestrator — the living index in one loop.

One ``tick`` (call it hourly) ties the pieces together:
  1. discover new / upgraded / removed models from the fetched catalog,
  2. decide what to grade now — anything new or upgraded (immediate provisional
     grade), plus provisional/stale cards due to advance toward confirmed,
  3. re-grade the due models within a hard budget, producing fresh GradeCards,
  4. hand back the updated state + a summary of what changed.

Every seam is injected (catalog fetch, grader, clock) so the loop is
deterministic and fully testable — no live API, no wall-clock in tests.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from handover.bench.discovery import CatalogModel, ModelChange, diff_catalog
from handover.bench.lifecycle import GradeCard, classify, next_cadence
from handover.metrics.core import Proportion
from handover.replay.budget import DailyBudget

# Grade one model now: returns (overall score, quality proportion with n + CI).
# Cost is charged to the budget by the grader itself.
Grader = Callable[[str], tuple[float | None, Proportion]]
CatalogFetch = Callable[[], Sequence[CatalogModel]]


class TickSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    changes: tuple[ModelChange, ...]
    graded: tuple[str, ...]
    skipped_budget: tuple[str, ...]
    n_provisional: int
    n_confirmed: int
    n_stale: int


class ContinuousState(BaseModel):
    model_config = ConfigDict(frozen=True)

    cards: dict[str, GradeCard]
    known_versions: dict[str, str]


def _due_to_advance(card: GradeCard, now: datetime) -> bool:
    """Provisional cards always advance; stale cards refresh. Confirmed & fresh hold."""
    fresh = classify(card.model_id, card.score, card.quality, card.updated_at, now)
    return fresh.status in ("provisional", "stale")


def tick(
    state: ContinuousState,
    fetch_catalog: CatalogFetch,
    grade: Grader,
    budget: DailyBudget,
    now: datetime,
    *,
    est_cost_per_grade: Decimal = Decimal("0.05"),
) -> tuple[ContinuousState, TickSummary]:
    catalog = list(fetch_catalog())
    changes = diff_catalog(catalog, state.known_versions)

    changed_ids = {c.model_id for c in changes if c.needs_grading}
    # Priority: new/upgraded first, then provisional/stale cards due to advance.
    due: list[str] = list(changed_ids)
    for model_id, card in state.cards.items():
        if model_id not in changed_ids and _due_to_advance(card, now):
            due.append(model_id)

    new_cards: dict[str, GradeCard] = dict(state.cards)
    graded: list[str] = []
    skipped: list[str] = []
    for model_id in due:
        if not budget.can_spend(est_cost_per_grade):
            skipped.append(model_id)
            continue
        score, quality = grade(model_id)  # grader charges the budget as it runs
        new_cards[model_id] = classify(model_id, score, quality, now, now)
        graded.append(model_id)

    # Refresh status (fresh -> stale) for cards not re-graded this tick.
    for model_id, card in list(new_cards.items()):
        if model_id not in graded:
            new_cards[model_id] = classify(model_id, card.score, card.quality, card.updated_at, now)

    known = {m.model_id: m.version_hint for m in catalog}
    summary = TickSummary(
        changes=tuple(changes),
        graded=tuple(graded),
        skipped_budget=tuple(skipped),
        n_provisional=sum(1 for c in new_cards.values() if c.status == "provisional"),
        n_confirmed=sum(1 for c in new_cards.values() if c.status == "confirmed"),
        n_stale=sum(1 for c in new_cards.values() if c.status == "stale"),
    )
    return ContinuousState(cards=new_cards, known_versions=known), summary


def publishable_cards(state: ContinuousState) -> list[GradeCard]:
    """Cards fit to show in the public ranking, best score first."""
    cards = [c for c in state.cards.values() if c.is_publishable]
    cards.sort(key=lambda c: c.score or -1.0, reverse=True)
    return cards


def cadence_plan(state: ContinuousState) -> dict[str, str]:
    """What sampling each graded model needs next — feeds the canary scheduler."""
    return {model_id: next_cadence(card) for model_id, card in state.cards.items()}


def initial_state(known_versions: Mapping[str, str] | None = None) -> ContinuousState:
    return ContinuousState(cards={}, known_versions=dict(known_versions or {}))
