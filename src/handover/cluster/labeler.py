"""Cluster labeling — the ONLY place in this module allowed to call a model.

Every call is pre-authorized against a hard budget (SPEC P6): when the next
call would exceed the cap, labeling stops — remaining clusters keep label=None.
The label prompt is built from representative-case METADATA only.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from handover.cluster.extractor import Cluster, Clustering
from handover.metrics.waste import TaskTraces


class LabelResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    cost_usd: Decimal


class LabelModel(Protocol):
    """Injected model client. Tests use a fake — never a live API (CLAUDE.md)."""

    def complete(self, prompt: str) -> LabelResult: ...


class BudgetExceededError(RuntimeError):
    pass


class SpendBudget:
    """Hard cap: exceeding stops the process, it does not warn (P6)."""

    def __init__(self, cap_usd: Decimal) -> None:
        self.cap_usd = cap_usd
        self.spent_usd = Decimal("0")

    def can_spend(self, estimate: Decimal) -> bool:
        return self.spent_usd + estimate <= self.cap_usd

    def charge(self, actual: Decimal) -> None:
        if self.spent_usd + actual > self.cap_usd:
            raise BudgetExceededError(f"spend {self.spent_usd + actual} exceeds cap {self.cap_usd}")
        self.spent_usd += actual


def _prompt_for(cluster: Cluster, items_by_task: Mapping[str, TaskTraces]) -> str:
    lines = [
        "Name this group of LLM tasks with a short lowercase label (2-4 words,",
        "like 'structured extraction' or 'code fix'). Metadata of representative cases:",
    ]
    for task_id in cluster.representative_task_ids:
        item = items_by_task.get(str(task_id))
        if item is None:
            continue
        trace = item.traces[-1]
        lines.append(
            f"- output={trace.output_shape.type} json_valid={trace.output_shape.json_valid} "
            f"code_blocks={trace.output_shape.n_code_blocks} "
            f"tools={'>'.join(c.name for c in trace.tool_calls) or 'none'} "
            f"attempts={item.task.attempts}"
        )
    lines.append("Reply with the label only.")
    return "\n".join(lines)


def label_clusters(
    clustering: Clustering,
    items: Sequence[TaskTraces],
    model: LabelModel,
    budget: SpendBudget,
    *,
    estimated_cost_per_call: Decimal = Decimal("0.01"),
) -> Clustering:
    items_by_task: dict[str, TaskTraces] = {str(item.task.task_id): item for item in items}
    labeled: list[Cluster] = []
    for cluster in clustering.clusters:  # cost-ranked: big clusters get labeled first
        if cluster.label is not None or not budget.can_spend(estimated_cost_per_call):
            labeled.append(cluster)
            continue
        result = model.complete(_prompt_for(cluster, items_by_task))
        budget.charge(result.cost_usd)
        labeled.append(cluster.model_copy(update={"label": result.text.strip().lower() or None}))
    return Clustering(clusters=tuple(labeled), assignments=clustering.assignments)


def apply_to_tasks(clustering: Clustering, items: Sequence[TaskTraces]) -> list[TaskTraces]:
    """Return items with each task's cluster_id filled from the clustering."""
    updated: list[TaskTraces] = []
    for item in items:
        cluster_id = clustering.assignments.get(str(item.task.task_id))
        if cluster_id is None:
            updated.append(item)
        else:
            updated.append(
                TaskTraces(
                    task=item.task.model_copy(update={"cluster_id": cluster_id}),
                    traces=item.traces,
                )
            )
    return updated
