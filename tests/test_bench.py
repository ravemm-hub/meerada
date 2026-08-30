"""Public-index bench runner: programmatic grading, budget stop, index output.
All models are FAKE — no live API (CLAUDE.md)."""

from decimal import Decimal

from handover.bench import ModelSpec, run_index, run_model
from handover.bench.tasks import SEED_TASKS, tasks_by_cluster
from handover.metrics.index import compute_index
from handover.replay.budget import DailyBudget


class FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text
        self.input_tokens = 100
        self.output_tokens = 40


def perfect_complete(system: str, user: str, max_tokens: int) -> FakeCompletion:
    """A model that passes every seed task — answers each by its content."""
    if "payee" in system:
        return FakeCompletion('{"name": "Acme", "amount": 1240.5, "currency": "USD"}')
    if "sum" in system:
        return FakeCompletion('{"sum": 108, "count": 6}')
    if "code block" in system:
        fn = "is_even"
        if "reverse_str" in user:
            fn = "reverse_str"
        elif "add(" in user:
            fn = "add"
        return FakeCompletion(f"```python\ndef {fn}(x):\n    return x\n```")
    if "sentiment" in system:
        low = user.lower()
        if "loved" in low or "flawless" in low:
            return FakeCompletion("positive")
        if "arrived on tuesday" in low or "package arrived" in low:
            return FakeCompletion("neutral")
        return FakeCompletion("negative")
    return FakeCompletion("")


def broken_complete(system: str, user: str, max_tokens: int) -> FakeCompletion:
    """A model that fails everything (never valid)."""
    return FakeCompletion("sorry, I cannot help with that")


def test_seed_tasks_are_all_verifiable() -> None:
    for task in SEED_TASKS:
        assert (task.json_schema is not None) ^ (task.contract_regex is not None)


def test_perfect_model_scores_all_clusters() -> None:
    spec = ModelSpec(
        model_id="m-good", price_in_per_mtok=Decimal("1"), price_out_per_mtok=Decimal("2")
    )
    per_cluster = run_model(spec, perfect_complete, DailyBudget(Decimal("100")))
    assert set(per_cluster) == set(tasks_by_cluster())
    for metrics in per_cluster.values():
        assert metrics.success_rate.value == 1.0
        assert metrics.cpat_usd.value is not None  # measured, so gradeable


def test_broken_model_scores_zero() -> None:
    spec = ModelSpec(
        model_id="m-bad", price_in_per_mtok=Decimal("1"), price_out_per_mtok=Decimal("2")
    )
    per_cluster = run_model(spec, broken_complete, DailyBudget(Decimal("100")))
    for metrics in per_cluster.values():
        assert metrics.success_rate.value == 0.0
        assert metrics.cpat_usd.value is None  # no wins -> no CPAT, not infinity


def test_budget_stops_the_run() -> None:
    spec = ModelSpec(
        model_id="m", price_in_per_mtok=Decimal("1000"), price_out_per_mtok=Decimal("1000")
    )
    budget = DailyBudget(Decimal("0.001"))  # room for ~0 tasks
    per_cluster = run_model(spec, perfect_complete, budget, est_cost_per_task=Decimal("0.01"))
    assert per_cluster == {} or all(m.n_tasks <= 1 for m in per_cluster.values())
    assert budget.spent_today() <= Decimal("0.001") + Decimal("0.2")  # never a blowout


def test_run_index_produces_a_ranking() -> None:
    specs = [
        ModelSpec(
            model_id="good", price_in_per_mtok=Decimal("5"), price_out_per_mtok=Decimal("15")
        ),
        ModelSpec(
            model_id="cheap", price_in_per_mtok=Decimal("0.1"), price_out_per_mtok=Decimal("0.4")
        ),
    ]

    def complete_for(spec: ModelSpec):
        # Both models are correct; "cheap" wins on value.
        return perfect_complete

    per_cluster = run_index(specs, complete_for, DailyBudget(Decimal("100")))
    cost_shares = {cluster: 1.0 / len(per_cluster) for cluster in per_cluster}
    ranking = compute_index(per_cluster, cost_shares)
    assert {e.model_id for e in ranking} == {"good", "cheap"}
    assert ranking[0].model_id == "cheap"  # same quality, lower cost -> higher grade
    assert all(e.score is not None for e in ranking)
