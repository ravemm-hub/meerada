"""T9 tests: taxonomy extraction on synthetic traffic, merge rule, determinism,
and the budget-capped labeler (fake model — never a live API)."""

from decimal import Decimal

from handover.assemble import assemble_grouped
from handover.cluster import (
    Clustering,
    LabelResult,
    SpendBudget,
    apply_to_tasks,
    extract_clusters,
    label_clusters,
)
from handover.metrics.waste import TaskTraces
from tests.factories import make_trace, task_of
from tests.synthetic import generate_records


def synthetic_items(n: int = 1200) -> list[TaskTraces]:
    grouped = assemble_grouped(generate_records(n))
    return [TaskTraces(task=task, traces=traces) for task, traces in grouped]


def test_extracts_reasonable_taxonomy_from_synthetic_traffic() -> None:
    items = synthetic_items()
    clustering = extract_clusters(items)
    # 12 synthetic templates -> expect a taxonomy in the 8-20 band, never more.
    assert 2 <= len(clustering.clusters) <= 20
    assert len(clustering.assignments) == len(items)  # every task assigned
    shares = sum(c.share_of_cost for c in clustering.clusters)
    assert abs(shares - 1.0) < 1e-6
    # Ranked by cost: c01 is the most expensive cluster.
    costs = [c.total_cost_usd for c in clustering.clusters]
    assert costs == sorted(costs, reverse=True)
    assert all(1 <= len(c.representative_task_ids) <= 5 for c in clustering.clusters)


def test_clustering_is_deterministic() -> None:
    items = synthetic_items(600)
    first = extract_clusters(items)
    second = extract_clusters(items)
    assert first.assignments == second.assignments


def test_over_split_taxonomy_is_merged() -> None:
    # 30 distinct templates, tiny groups each -> must merge to <= 15.
    items = []
    start = 0
    for template_index in range(30):
        for _ in range(6):
            items.append(
                task_of(
                    make_trace(
                        start_s=start, status="pass", template=f"tpl {chr(65 + template_index)}"
                    )
                )
            )
            start += 400
    clustering = extract_clusters(items, min_cluster_size=3)
    assert len(clustering.clusters) <= 15
    assert len(clustering.assignments) == len(items)


def test_empty_input() -> None:
    assert extract_clusters([]) == Clustering(clusters=(), assignments={})


class FakeModel:
    def __init__(self, cost: str = "0.01") -> None:
        self.calls = 0
        self.cost = Decimal(cost)

    def complete(self, prompt: str) -> LabelResult:
        assert "Metadata of representative cases" in prompt
        self.calls += 1
        return LabelResult(text=f"Label {self.calls}", cost_usd=self.cost)


def test_labeler_labels_within_budget_and_stops_at_cap() -> None:
    items = synthetic_items(600)
    clustering = extract_clusters(items)
    n_clusters = len(clustering.clusters)
    assert n_clusters >= 3

    model = FakeModel()
    budget = SpendBudget(cap_usd=Decimal("0.03"))  # room for exactly 3 calls
    labeled = label_clusters(clustering, items, model, budget)

    assert model.calls == 3  # stopped BEFORE exceeding, not after (P6)
    assert budget.spent_usd == Decimal("0.03")
    got = [c.label for c in labeled.clusters]
    assert got[:3] == ["label 1", "label 2", "label 3"]  # cost-ranked order, lowercased
    assert all(label is None for label in got[3:])


def test_labeler_full_budget_labels_everything() -> None:
    items = synthetic_items(600)
    clustering = extract_clusters(items)
    model = FakeModel()
    labeled = label_clusters(clustering, items, model, SpendBudget(Decimal("10")))
    assert all(c.label for c in labeled.clusters)
    assert model.calls == len(clustering.clusters)


def test_apply_to_tasks_fills_cluster_id() -> None:
    items = synthetic_items(400)
    clustering = extract_clusters(items)
    updated = apply_to_tasks(clustering, items)
    assert all(item.task.cluster_id is not None for item in updated)
    assert updated[0].task.cluster_id == clustering.assignments[str(updated[0].task.task_id)]
