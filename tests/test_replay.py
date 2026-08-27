"""T12 tests: dedup, cache-key ordering, batch mode, the hard daily budget
(stops, never overruns), day rollover, and stratified live sampling."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from handover.metrics.waste import TaskTraces
from handover.pack.goldset import build_goldset
from handover.replay import (
    DailyBudget,
    ReplayCase,
    ReplayResult,
    cases_from_goldset,
    replay,
    sample_live_traffic,
)
from tests.factories import make_trace, task_of


def make_case(fingerprint: str, cache_key: str = "tpl-A", cluster: str = "c01") -> ReplayCase:
    return ReplayCase(
        case_id=uuid4(),
        cluster_id=cluster,
        input_ref="trace://x/input",
        expected_ref="trace://x/output",
        verifier_spec="test_exit_code",
        input_fingerprint=fingerprint,
        cache_key=cache_key,
    )


class FakeClient:
    def __init__(self, cost: str = "0.01", supports_batch: bool = False) -> None:
        self.model_id = "candidate-model"
        self.supports_batch = supports_batch
        self.cost = Decimal(cost)
        self.calls: list[str] = []
        self.batch_sizes: list[int] = []

    def run(self, case: ReplayCase) -> ReplayResult:
        self.calls.append(case.cache_key)
        return ReplayResult(output_ref="trace://out", cost_usd=self.cost, latency_ms=100)

    def run_batch(self, cases: list[ReplayCase]) -> list[ReplayResult]:
        self.batch_sizes.append(len(cases))
        return [self.run(case) for case in cases]


def always_pass(case: ReplayCase, result: ReplayResult) -> bool:
    return True


def big_budget() -> DailyBudget:
    return DailyBudget(Decimal("100"))


def test_dedup_by_input_fingerprint() -> None:
    cases = [make_case("fp-1"), make_case("fp-1"), make_case("fp-2")]
    client = FakeClient()
    report = replay(cases, client, always_pass, big_budget())
    assert report.n_run == 2  # fp-1 ran once
    assert report.n_deduped == 1
    deduped = next(o for o in report.outcomes if o.deduped)
    assert deduped.passed is True
    assert deduped.cost_usd == Decimal("0")
    assert report.total_cost_usd == Decimal("0.02")


def test_cases_ordered_by_cache_key_for_prompt_caching() -> None:
    cases = [
        make_case("f1", cache_key="tpl-B"),
        make_case("f2", cache_key="tpl-A"),
        make_case("f3", cache_key="tpl-B"),
        make_case("f4", cache_key="tpl-A"),
    ]
    client = FakeClient()
    replay(cases, client, always_pass, big_budget())
    assert client.calls == ["tpl-A", "tpl-A", "tpl-B", "tpl-B"]


def test_batch_api_used_when_supported() -> None:
    cases = [make_case(f"fp-{i}") for i in range(120)]
    client = FakeClient(supports_batch=True)
    report = replay(cases, client, always_pass, big_budget())
    assert client.batch_sizes == [50, 50, 20]
    assert report.n_run == 120


def test_budget_stops_and_never_overruns() -> None:
    cases = [make_case(f"fp-{i}") for i in range(10)]
    client = FakeClient(cost="0.01")
    budget = DailyBudget(Decimal("0.03"))
    report = replay(cases, client, always_pass, budget)
    assert report.budget_stopped is True
    assert report.n_run == 3
    assert report.n_skipped_budget == 7
    assert budget.spent_today() == Decimal("0.03")  # never over the cap
    skipped = [o for o in report.outcomes if o.passed is None]
    assert len(skipped) == 7
    assert all(o.cost_usd == Decimal("0") for o in skipped)


def test_batch_shrinks_before_stopping() -> None:
    cases = [make_case(f"fp-{i}") for i in range(60)]
    client = FakeClient(cost="0.01", supports_batch=True)
    budget = DailyBudget(Decimal("0.51"))  # room for one 50-batch + one single
    report = replay(cases, client, always_pass, budget)
    assert client.batch_sizes[0] == 50
    assert 1 in client.batch_sizes  # shrank instead of giving up
    assert budget.spent_today() <= Decimal("0.51")
    assert report.budget_stopped is True


def test_daily_budget_resets_at_day_boundary() -> None:
    day = [datetime(2026, 8, 27, 23, 0, tzinfo=UTC)]
    budget = DailyBudget(Decimal("0.02"), clock=lambda: day[0])
    budget.record(Decimal("0.02"))
    assert budget.remaining() == Decimal("0")
    day[0] = datetime(2026, 8, 28, 1, 0, tzinfo=UTC)
    assert budget.remaining() == Decimal("0.02")


def test_verifier_verdict_is_recorded() -> None:
    cases = [make_case("fp-1"), make_case("fp-2")]
    verdicts = iter([True, False])
    report = replay(cases, FakeClient(), lambda c, r: next(verdicts), big_budget())
    assert [o.passed for o in report.outcomes].count(True) == 1
    assert [o.passed for o in report.outcomes].count(False) == 1


def test_cases_from_goldset_carries_fingerprints() -> None:
    items = [task_of(make_trace(start_s=i * 400, status="pass")) for i in range(5)]
    goldset = build_goldset("c01", items)
    cases = cases_from_goldset(goldset, items)
    assert len(cases) == 5
    assert all(c.input_fingerprint.startswith("sha256:") for c in cases)
    assert all(c.cache_key.startswith("sha256:") for c in cases)


def test_stratified_sampling_weights_by_cost_share() -> None:
    items: list[TaskTraces] = []
    assignments: dict[str, str] = {}
    for i in range(300):
        item = task_of(make_trace(start_s=i * 400, status="pass", template="tpl expensive"))
        items.append(item)
        assignments[str(item.task.task_id)] = "c01"
    for i in range(300):
        item = task_of(make_trace(start_s=(400 + i) * 400, status="pass", template="tpl cheap"))
        items.append(item)
        assignments[str(item.task.task_id)] = "c02"

    shares = {"c01": 0.9, "c02": 0.1}
    sampled = sample_live_traffic(items, assignments, shares, fraction=0.05)
    by_cluster = {"c01": 0, "c02": 0}
    for item in sampled:
        by_cluster[assignments[str(item.task.task_id)]] += 1
    assert by_cluster["c01"] > by_cluster["c02"]
    assert by_cluster["c02"] >= 1  # every cluster keeps a foothold

    again = sample_live_traffic(items, assignments, shares, fraction=0.05)
    assert [str(i.task.task_id) for i in sampled] == [str(i.task.task_id) for i in again]
