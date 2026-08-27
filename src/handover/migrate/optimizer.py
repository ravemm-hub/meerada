"""Bounded prompt-optimization loop for failing clusters (SPEC §7.3 FIX).

Hard limits, no exceptions: max 8 iterations per cluster, an explicit budget
(a required positional argument — this module is impossible to run without
one), and early stop when improvement is under 1 point across two consecutive
iterations. Every iteration is logged with its cost.
"""

from collections.abc import Callable
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from handover.cluster.labeler import SpendBudget

MAX_ITERATIONS = 8
MIN_IMPROVEMENT_POINTS = 1.0

# (current_best_prompt, iteration_index) -> (variant_prompt, generation_cost)
VariantGenerator = Callable[[str, int], tuple[str, Decimal]]
# variant_prompt -> (pass_rate 0..1 on the failing cluster's golden cases, eval_cost)
VariantEvaluator = Callable[[str], tuple[float, Decimal]]


class Iteration(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    pass_rate: float
    cost_usd: Decimal
    improvement_points: float  # vs the best rate before this iteration
    accepted: bool


class OptimizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    cluster_id: str
    base_pass_rate: float
    best_pass_rate: float
    best_prompt: str
    iterations: tuple[Iteration, ...]
    total_cost_usd: Decimal
    stop_reason: str  # max_iterations | plateau | budget


def optimize_cluster(
    cluster_id: str,
    base_prompt: str,
    base_pass_rate: float,
    generate: VariantGenerator,
    evaluate: VariantEvaluator,
    budget: SpendBudget,
    *,
    max_iterations: int = MAX_ITERATIONS,
    min_improvement_points: float = MIN_IMPROVEMENT_POINTS,
    estimated_cost_per_iteration: Decimal = Decimal("0.05"),
) -> OptimizationResult:
    best_prompt = base_prompt
    best_rate = base_pass_rate
    iterations: list[Iteration] = []
    small_streak = 0
    stop_reason = "max_iterations"

    for index in range(max_iterations):
        if not budget.can_spend(estimated_cost_per_iteration):
            stop_reason = "budget"
            break

        variant, generation_cost = generate(best_prompt, index)
        pass_rate, evaluation_cost = evaluate(variant)
        cost = generation_cost + evaluation_cost
        budget.charge(cost)

        improvement = (pass_rate - best_rate) * 100
        accepted = pass_rate > best_rate
        iterations.append(
            Iteration(
                index=index,
                pass_rate=pass_rate,
                cost_usd=cost,
                improvement_points=round(improvement, 2),
                accepted=accepted,
            )
        )
        if accepted:
            best_prompt, best_rate = variant, pass_rate

        if improvement < min_improvement_points:
            small_streak += 1
            if small_streak >= 2:
                stop_reason = "plateau"
                break
        else:
            small_streak = 0

    return OptimizationResult(
        cluster_id=cluster_id,
        base_pass_rate=base_pass_rate,
        best_pass_rate=best_rate,
        best_prompt=best_prompt,
        iterations=tuple(iterations),
        total_cost_usd=sum((i.cost_usd for i in iterations), Decimal("0")),
        stop_reason=stop_reason,
    )
