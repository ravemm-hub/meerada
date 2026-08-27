"""T6 tests: exact §4.1 formulas, Wilson intervals, waste components with
evidence grades, and the required properties (CPAT never below mean cost per
attempt; zero successes yields None, not infinity)."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from handover.metrics import (
    ModelPrice,
    by_model,
    compute_core,
    compute_waste,
    proportion,
    wilson_interval,
)
from tests.factories import make_task, make_trace, task_of

PRICES = {
    "model-a": ModelPrice(input_per_mtok=Decimal("3"), output_per_mtok=Decimal("10")),
}


def test_wilson_interval_known_value() -> None:
    low, high = wilson_interval(90, 100)
    assert 0.82 < low < 0.83
    assert 0.93 < high < 0.95


def test_proportion_zero_n_is_none() -> None:
    result = proportion(0, 0)
    assert result.value is None
    assert result.n == 0


def test_core_metrics_basic() -> None:
    tasks = [
        make_task(attempts=2, succeeded=True, cost="0.25", wall_ms=60000),
        make_task(attempts=1, succeeded=False, cost="0.10", wall_ms=30000),
        make_task(attempts=1, succeeded=True, cost="0.05", wall_ms=10000),
    ]
    metrics = compute_core(tasks)
    assert metrics.n_verified == 3
    assert metrics.success_rate.value == 2 / 3
    assert metrics.cpat_usd.value == Decimal("0.20")  # 0.40 total / 2 wins
    assert metrics.ttat_seconds.value == 50.0  # 100s total / 2 wins
    assert metrics.attempts_per_win.value == 2.0  # 4 attempts / 2 wins
    assert metrics.success_rate.ci_low is not None
    assert metrics.success_rate.ci_high is not None


def test_zero_successes_returns_none_not_infinity() -> None:
    metrics = compute_core([make_task(succeeded=False), make_task(succeeded=False)])
    assert metrics.cpat_usd.value is None
    assert metrics.ttat_seconds.value is None
    assert metrics.attempts_per_win.value is None
    assert metrics.success_rate.value == 0.0


def test_unknown_tasks_are_excluded() -> None:
    with_unknown = [
        make_task(succeeded=True, cost="0.10"),
        make_task(succeeded=False, cost="99.0", grade="unknown"),
    ]
    metrics = compute_core(with_unknown)
    assert metrics.n_unknown == 1
    assert metrics.n_verified == 1
    assert metrics.cpat_usd.value == Decimal("0.10")
    assert metrics.unknown_rate.value == 0.5


def test_by_model_groups_by_finishing_model() -> None:
    tasks = [
        make_task(succeeded=True, model="model-a"),
        make_task(succeeded=True, model="model-b"),
        make_task(succeeded=False, model="model-b"),
    ]
    grouped = by_model(tasks)
    assert set(grouped) == {"model-a", "model-b"}
    assert grouped["model-b"].n_verified == 2


@st.composite
def task_lists(draw: st.DrawFn) -> list:
    n = draw(st.integers(min_value=1, max_value=25))
    tasks = []
    for _ in range(n):
        tasks.append(
            make_task(
                attempts=draw(st.integers(min_value=1, max_value=5)),
                succeeded=draw(st.booleans()),
                cost=draw(
                    st.decimals(
                        min_value=Decimal("0"),
                        max_value=Decimal("10"),
                        places=4,
                        allow_nan=False,
                        allow_infinity=False,
                    )
                ),
                wall_ms=draw(st.integers(min_value=0, max_value=600000)),
            )
        )
    return tasks


@given(task_lists())
def test_cpat_never_below_mean_cost_per_attempt(tasks: list) -> None:
    metrics = compute_core(tasks)
    total_cost = sum((t.total_cost_usd for t in tasks), Decimal("0"))
    total_attempts = sum(t.attempts for t in tasks)
    if metrics.cpat_usd.value is None:
        assert not any(t.succeeded for t in tasks)
    else:
        assert metrics.cpat_usd.value >= total_cost / total_attempts
        assert metrics.attempts_per_win.value is not None
        assert metrics.attempts_per_win.value >= 1.0


@given(task_lists())
def test_success_rate_ci_brackets_value(tasks: list) -> None:
    rate = compute_core(tasks).success_rate
    assert rate.value is not None
    assert rate.ci_low is not None and rate.ci_high is not None
    assert 0.0 <= rate.ci_low <= rate.value <= rate.ci_high <= 1.0


def test_waste_retry_and_dead_are_measured() -> None:
    winner = task_of(
        make_trace(start_s=0, status="fail", cost="0.10"),
        make_trace(start_s=60, status="pass", cost="0.15"),
    )
    dead = task_of(make_trace(start_s=200, status="fail", cost="0.20", template="t-dead"))
    waste = compute_waste([winner, dead], PRICES)
    assert waste.retry.amount_usd == Decimal("0.10")
    assert waste.retry.evidence_grade == "measured"
    assert waste.dead.amount_usd == Decimal("0.20")
    assert waste.dead.evidence_grade == "measured"
    assert waste.total_usd == Decimal("0.30")


def test_waste_reasoning_is_derived_excess_over_median() -> None:
    lean = task_of(make_trace(start_s=0, status="pass", reasoning_tokens=100))
    heavy = task_of(make_trace(start_s=500, status="pass", reasoning_tokens=300))
    waste = compute_waste([lean, heavy], PRICES)
    # median of successes = 200; excess = 100 tokens at $10/Mtok
    assert waste.reasoning.amount_usd == Decimal("0.001")
    assert waste.reasoning.evidence_grade == "derived"
    assert waste.reasoning.n_traces == 1


def test_waste_context_counts_repeat_uncached_prefixes() -> None:
    first = task_of(make_trace(start_s=0, status="pass", input_tokens=1000))
    repeat = task_of(make_trace(start_s=500, status="pass", input_tokens=1000))
    waste = compute_waste([first, repeat], PRICES)
    # first occurrence establishes the prefix; the repeat could have cached 1000 tokens at $3/Mtok
    assert waste.context.amount_usd == Decimal("0.003")
    assert waste.context.evidence_grade == "derived"
    assert waste.context.n_traces == 1


def test_waste_unpriced_models_are_counted_not_guessed() -> None:
    first = task_of(make_trace(start_s=0, status="pass", input_tokens=1000, model="mystery"))
    repeat = task_of(make_trace(start_s=500, status="pass", input_tokens=1000, model="mystery"))
    waste = compute_waste([first, repeat], PRICES)
    assert waste.context.amount_usd == Decimal("0")
    assert waste.n_unpriced_traces == 1


def test_waste_excludes_unknown_tasks() -> None:
    ghost = task_of(make_trace(start_s=0, status="unknown", cost="5.00"))
    waste = compute_waste([ghost], PRICES)
    assert waste.total_usd == Decimal("0")
    assert waste.dead.n_traces == 0
