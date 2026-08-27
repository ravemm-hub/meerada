"""T13-T15 tests: translator drafts with diffs, gap-report verdicts with
Newcombe significance, and the bounded optimization loop."""

from decimal import Decimal
from uuid import uuid4

from handover.cluster.extractor import Cluster, Clustering
from handover.cluster.labeler import SpendBudget
from handover.metrics import compute_core
from handover.migrate import (
    build_gap_report,
    format_gap_report,
    optimize_cluster,
    translate_prompts,
)
from handover.migrate.translator import TranslationResult
from handover.replay.runner import CaseOutcome, ReplayReport
from tests.factories import make_task

SOURCE_PROMPT = "You are an invoice extraction engine.\nAlways return JSON."


class FakeTranslator:
    def __init__(self, cost: str = "0.02") -> None:
        self.cost = Decimal(cost)
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> TranslationResult:
        self.prompts.append(prompt)
        return TranslationResult(
            text=(
                '{"translated": "You are an invoice extraction engine.\\n'
                '<output>JSON only</output>", "rationale": ["added XML output tag"]}'
            ),
            cost_usd=self.cost,
        )


def test_translator_produces_diff_and_rationale_never_applies() -> None:
    model = FakeTranslator()
    budget = SpendBudget(Decimal("1"))
    (result,) = translate_prompts({"c01": SOURCE_PROMPT}, "claude-sonnet-5", model, budget)
    assert result.applied is False
    assert result.error is None
    assert result.rationale == ("added XML output tag",)
    assert "-Always return JSON." in result.diff
    assert "+<output>JSON only</output>" in result.diff
    assert "Claude conventions" in model.prompts[0]  # target hints selected
    assert SOURCE_PROMPT.splitlines()[0] in model.prompts[0]


def test_translator_handles_bad_model_json() -> None:
    class Broken:
        def complete(self, prompt: str) -> TranslationResult:
            return TranslationResult(text="not json at all", cost_usd=Decimal("0.02"))

    (result,) = translate_prompts(
        {"c01": SOURCE_PROMPT}, "gpt-5.6", Broken(), SpendBudget(Decimal("1"))
    )
    assert result.translated_text is None
    assert result.error is not None


def test_translator_respects_budget() -> None:
    model = FakeTranslator(cost="0.02")
    budget = SpendBudget(Decimal("0.04"))  # room for 2 of 3 clusters
    results = translate_prompts(
        {"c01": SOURCE_PROMPT, "c02": SOURCE_PROMPT, "c03": SOURCE_PROMPT},
        "claude-sonnet-5",
        model,
        budget,
    )
    assert len(model.prompts) == 2
    assert [r.error is None for r in results] == [True, True, False]
    assert "budget" in (results[2].error or "")


def make_clustering() -> Clustering:
    def cluster(cid: str, share: float, label: str) -> Cluster:
        return Cluster(
            cluster_id=cid,
            n_tasks=100,
            total_cost_usd=Decimal("10"),
            share_of_cost=share,
            representative_task_ids=(uuid4(),),
            label=label,
        )

    return Clustering(
        clusters=(
            cluster("c01", 0.5, "structured extract"),
            cluster("c02", 0.3, "summarize"),
            cluster("c03", 0.2, "long agentic"),
        ),
        assignments={},
    )


def replay_outcomes(cluster_id: str, n: int, wins: int) -> list[CaseOutcome]:
    return [
        CaseOutcome(
            case_id=uuid4(),
            cluster_id=cluster_id,
            passed=i < wins,
            cost_usd=Decimal("0.01"),
            latency_ms=2000,
            deduped=False,
        )
        for i in range(n)
    ]


def test_gap_report_verdicts_and_no_data() -> None:
    baselines = {
        "c01": compute_core([make_task(succeeded=i < 180, wall_ms=60000) for i in range(200)]),
        "c02": compute_core([make_task(succeeded=i < 180, wall_ms=60000) for i in range(200)]),
    }
    report = ReplayReport(
        model_id="candidate",
        outcomes=tuple(
            replay_outcomes("c01", 60, 24)  # 40% vs 90% -> significant drop
            + replay_outcomes("c02", 60, 57)  # 95% vs 90% -> fine
        ),
        total_cost_usd=Decimal("1.2"),
        n_run=120,
        n_deduped=0,
        n_skipped_budget=0,
        budget_stopped=False,
    )
    gap = build_gap_report(
        make_clustering(),
        baselines,
        report,
        "incumbent",
        edge_case_counts={"c01": 3},
    )
    assert gap.n_block == 1 and gap.n_pass == 1
    assert gap.n_no_data == 1  # c03 never replayed
    blocked = next(g for g in gap.clusters if g.verdict == "BLOCK")
    assert blocked.cluster_id == "c01"
    assert blocked.ci_high_points < 0  # the drop is statistically real
    assert blocked.engineer_days is not None and 1 <= blocked.engineer_days <= 15
    passed = next(g for g in gap.clusters if g.verdict == "PASS")
    assert passed.engineer_days is None

    text = format_gap_report(gap)
    assert "structured extract" in text and "BLOCK" in text
    assert "1/2 clusters pass" in text
    assert "engineer-days" in text


def test_gap_report_small_insignificant_drop_passes() -> None:
    baselines = {
        "c01": compute_core([make_task(succeeded=i < 90, wall_ms=60000) for i in range(100)]),
    }
    report = ReplayReport(
        model_id="candidate",
        outcomes=tuple(replay_outcomes("c01", 30, 26)),  # 86.7% vs 90%: n too small
        total_cost_usd=Decimal("0.3"),
        n_run=30,
        n_deduped=0,
        n_skipped_budget=0,
        budget_stopped=False,
    )
    gap = build_gap_report(make_clustering(), baselines, report, "incumbent")
    assert gap.clusters[0].verdict == "PASS"  # no premature BLOCK without significance


def test_optimizer_stops_on_plateau_and_tracks_best() -> None:
    rates = iter([0.75, 0.80, 0.803, 0.804, 0.9])  # after two <1pt steps: plateau

    def generate(prompt: str, index: int) -> tuple[str, Decimal]:
        return f"{prompt} v{index}", Decimal("0.01")

    def evaluate(prompt: str) -> tuple[float, Decimal]:
        return next(rates), Decimal("0.02")

    result = optimize_cluster(
        "c01", "base prompt", 0.70, generate, evaluate, SpendBudget(Decimal("10"))
    )
    assert result.stop_reason == "plateau"
    assert len(result.iterations) == 4
    assert result.best_pass_rate == 0.804  # tiny gains still accepted, then plateau stops
    assert result.best_prompt.startswith("base prompt")
    assert all(i.cost_usd == Decimal("0.03") for i in result.iterations)


def test_optimizer_hard_budget_stop() -> None:
    def generate(prompt: str, index: int) -> tuple[str, Decimal]:
        return prompt, Decimal("0.03")

    def evaluate(prompt: str) -> tuple[float, Decimal]:
        return 0.99, Decimal("0.02")

    budget = SpendBudget(Decimal("0.12"))
    result = optimize_cluster(
        "c01",
        "base",
        0.5,
        generate,
        evaluate,
        budget,
        estimated_cost_per_iteration=Decimal("0.05"),
    )
    assert result.stop_reason == "budget"
    assert len(result.iterations) == 2
    assert budget.spent_usd <= Decimal("0.12")


def test_optimizer_max_iterations() -> None:
    counter = iter(range(100))

    def generate(prompt: str, index: int) -> tuple[str, Decimal]:
        return f"v{index}", Decimal("0.01")

    def evaluate(prompt: str) -> tuple[float, Decimal]:
        return 0.5 + 0.02 * next(counter), Decimal("0.01")

    result = optimize_cluster("c01", "base", 0.5, generate, evaluate, SpendBudget(Decimal("10")))
    assert result.stop_reason == "max_iterations"
    assert len(result.iterations) == 8  # never more
