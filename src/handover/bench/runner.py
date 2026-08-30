"""Public-index benchmark runner (SPEC §6.2 canary + §4.3 index).

Runs the verifiable task set on each model through an injected ``complete``
callable (any ProviderClient's caller), verifies every output programmatically
(grade-A measured only), and produces the per-cluster CoreMetrics the index
consumes. A hard daily budget caps spend; the run stops rather than overruns.
"""

import time
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from handover.bench.tasks import BenchTask, tasks_by_cluster
from handover.metrics.core import CoreMetrics, compute_core
from handover.replay.budget import DailyBudget
from handover.schema.task import Task, TaskTokens
from handover.verify import Artifacts, default_registry


class ModelSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    price_in_per_mtok: Decimal
    price_out_per_mtok: Decimal


class _Completion(Protocol):
    text: str
    input_tokens: int
    output_tokens: int


# (system, user, max_tokens) -> completion. Wraps any provider client's caller.
Complete = Callable[[str, str, int], _Completion]


def _verify(task: BenchTask, output_text: str) -> bool:
    artifacts = Artifacts(
        output_text=output_text,
        json_schema=task.json_schema,
        contract_regex=task.contract_regex,
    )
    return default_registry().verify(_placeholder_task(), artifacts).status == "pass"


def _placeholder_task() -> Task:
    from uuid import UUID

    return Task(
        task_id=UUID(int=0),
        tenant_id=UUID(int=0),
        attempts=1,
        succeeded=False,
        first_attempt_success=False,
        total_cost_usd=Decimal("0"),
        total_wall_ms=0,
        total_tokens=TaskTokens(input=0, output=0, reasoning=0),
        models_used=("bench",),
        verification_grade="unknown",
    )


def run_model(
    spec: ModelSpec,
    complete: Complete,
    budget: DailyBudget,
    *,
    max_tokens: int = 512,
    est_cost_per_task: Decimal = Decimal("0.01"),
    repeats: int = 1,
) -> dict[str, CoreMetrics]:
    """Run the seed task set on one model; return per-cluster metrics.

    Each task becomes one Task graded measured pass/fail — so the index score
    rests entirely on programmatic verification. ``repeats`` re-runs the set to
    build a larger sample (n) toward the publishable / confirmed thresholds.
    """
    per_cluster: dict[str, CoreMetrics] = {}
    for cluster, base_tasks in tasks_by_cluster().items():
        tasks = list(base_tasks) * repeats
        graded: list[Task] = []
        for task in tasks:
            if not budget.can_spend(est_cost_per_task):
                break  # hard stop, never overrun (P6)
            start = time.monotonic()
            completion = complete(task.system, task.user, max_tokens)
            wall_ms = max(1, int((time.monotonic() - start) * 1000))
            cost = (
                Decimal(completion.input_tokens) * spec.price_in_per_mtok
                + Decimal(completion.output_tokens) * spec.price_out_per_mtok
            ) / Decimal(1_000_000)
            budget.record(cost)
            passed = _verify(task, completion.text)
            graded.append(
                Task(
                    task_id=__import__("uuid").uuid4(),
                    tenant_id=__import__("uuid").UUID(int=0),
                    attempts=1,
                    succeeded=passed,
                    first_attempt_success=passed,
                    total_cost_usd=cost,
                    total_wall_ms=wall_ms,
                    total_tokens=TaskTokens(
                        input=completion.input_tokens, output=completion.output_tokens, reasoning=0
                    ),
                    models_used=(spec.model_id,),
                    verification_grade="measured",
                )
            )
        if graded:
            per_cluster[cluster] = compute_core(graded)
    return per_cluster


def run_index(
    specs: list[ModelSpec],
    complete_for: Callable[[ModelSpec], Complete],
    budget: DailyBudget,
) -> dict[str, dict[str, CoreMetrics]]:
    """Run every model; return {cluster: {model_id: CoreMetrics}} for the index."""
    by_model: dict[str, dict[str, CoreMetrics]] = {}
    for spec in specs:
        by_model[spec.model_id] = run_model(spec, complete_for(spec), budget)

    per_cluster: dict[str, dict[str, CoreMetrics]] = {}
    for model_id, clusters in by_model.items():
        for cluster, metrics in clusters.items():
            per_cluster.setdefault(cluster, {})[model_id] = metrics
    return per_cluster
