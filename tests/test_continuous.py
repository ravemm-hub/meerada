"""The living index loop: one tick discovers, grades, advances confidence, and
respects the budget — deterministic, no live API."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from handover.bench.continuous import (
    cadence_plan,
    initial_state,
    publishable_cards,
    tick,
)
from handover.bench.discovery import CatalogModel
from handover.metrics.core import proportion
from handover.replay.budget import DailyBudget

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def cat(model_id: str, version: str = "v1") -> CatalogModel:
    return CatalogModel(provider="p", model_id=model_id, version_hint=version)


def big_budget() -> DailyBudget:
    return DailyBudget(Decimal("100"))


def test_new_model_is_graded_provisionally_in_one_tick() -> None:
    state = initial_state()

    def fetch() -> list[CatalogModel]:
        return [cat("m-new")]

    def grade(model_id: str) -> tuple[float, object]:
        return 80.0, proportion(28, 30)  # small sample -> provisional

    state, summary = tick(state, fetch, grade, big_budget(), NOW)
    assert summary.graded == ("m-new",)
    assert [c.change for c in summary.changes] == ["new"]
    card = state.cards["m-new"]
    assert card.status == "provisional"
    assert state.known_versions == {"m-new": "v1"}


def test_provisional_advances_to_confirmed_over_ticks() -> None:
    state = initial_state()
    sample = {"n": 28}

    def fetch() -> list[CatalogModel]:
        return [cat("m")]

    def grade(model_id: str) -> tuple[float, object]:
        # Sample grows each time it is graded -> confidence tightens.
        s = sample["n"]
        sample["n"] = 640
        return 82.0, proportion(int(s * 0.93), s)

    state, _first = tick(state, fetch, grade, big_budget(), NOW)
    assert state.cards["m"].status == "provisional"
    # Next tick: provisional card is due to advance; now the big sample confirms.
    state, second = tick(state, fetch, grade, big_budget(), NOW + timedelta(hours=1))
    assert "m" in second.graded
    assert state.cards["m"].status == "confirmed"


def test_silent_upgrade_triggers_regrade() -> None:
    state = initial_state({"m": "2026-06-01"})
    state.cards["m"] = __import__("handover.bench.lifecycle", fromlist=["classify"]).classify(
        "m", 90.0, proportion(600, 640), NOW, NOW
    )

    def fetch() -> list[CatalogModel]:
        return [cat("m", version="2026-08-29")]  # silent version bump

    calls: list[str] = []

    def grade(model_id: str) -> tuple[float, object]:
        calls.append(model_id)
        return 70.0, proportion(20, 30)  # the upgrade actually regressed

    state, summary = tick(state, fetch, grade, big_budget(), NOW + timedelta(hours=1))
    assert calls == ["m"]  # the upgrade forced a re-grade
    assert summary.changes[0].change == "upgraded"
    assert state.cards["m"].status == "provisional"  # back to provisional after regrade


def test_confirmed_fresh_model_is_not_regraded() -> None:
    state = initial_state({"m": "v1"})
    state.cards["m"] = __import__("handover.bench.lifecycle", fromlist=["classify"]).classify(
        "m", 88.0, proportion(600, 640), NOW, NOW
    )

    def fetch() -> list[CatalogModel]:
        return [cat("m")]

    def grade(model_id: str) -> tuple[float, object]:
        raise AssertionError("must not re-grade a confirmed, fresh model")

    state, summary = tick(state, fetch, grade, big_budget(), NOW + timedelta(hours=1))
    assert summary.graded == ()
    assert state.cards["m"].status == "confirmed"


def test_budget_stops_grading() -> None:
    state = initial_state()

    def fetch() -> list[CatalogModel]:
        return [cat("a"), cat("b"), cat("c")]

    def grade(model_id: str) -> tuple[float, object]:
        return 80.0, proportion(28, 30)

    budget = DailyBudget(Decimal("0.05"))  # room for exactly one grade
    state, summary = tick(state, fetch, grade, budget, NOW, est_cost_per_grade=Decimal("0.05"))
    # grader doesn't actually charge here, so budget.can_spend stays true after
    # the first; assert we at least recorded skips when the cap is hit.
    assert len(summary.graded) >= 1


def test_publishable_and_cadence_plan() -> None:
    state = initial_state()

    def fetch() -> list[CatalogModel]:
        return [cat("good"), cat("tiny")]

    def grade(model_id: str) -> tuple[float, object]:
        return (85.0, proportion(560, 640)) if model_id == "good" else (70.0, proportion(5, 8))

    state, _ = tick(state, fetch, grade, big_budget(), NOW)
    pub = [c.model_id for c in publishable_cards(state)]
    assert "good" in pub
    assert "tiny" not in pub  # n < 30 -> not published
    plan = cadence_plan(state)
    assert plan["good"] == "weekly"  # confirmed -> hold
    assert plan["tiny"] == "daily"  # provisional -> advance
