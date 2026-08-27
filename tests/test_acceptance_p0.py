"""P0 acceptance (TASKS.md): 10,000 synthetic traces across 3 models with
realistic retry patterns, ingested end to end, rendered to the HTML report.
Fails if the unknown-rate exceeds 30%."""

from pathlib import Path

from handover.assemble import assemble_grouped
from handover.metrics import TaskTraces, by_model, compute_core, compute_waste
from handover.report import build_model_reports, render_report
from handover.report.__main__ import DEFAULT_PRICES
from tests.synthetic import generate_records

OUT = Path(__file__).parent.parent / "out" / "p0_report.html"


def test_p0_acceptance_end_to_end() -> None:
    records = generate_records(10_000)
    assert len(records) == 10_000

    grouped = assemble_grouped(records)
    tasks = [task for task, _ in grouped]
    overall = compute_core(tasks)

    # Acceptance gate: unknown-rate below 30%.
    assert overall.unknown_rate.value is not None
    assert overall.unknown_rate.value < 0.30

    # Sanity: retries exist, failures exist, all three models present.
    assert any(task.attempts > 1 for task in tasks)
    assert any(not task.succeeded for task in tasks)
    per_model = by_model(tasks)
    assert set(per_model) == {"model-alpha", "model-beta", "model-gamma"}
    for metrics in per_model.values():
        assert metrics.cpat_usd.value is not None

    items = [TaskTraces(task=task, traces=traces) for task, traces in grouped]
    waste = compute_waste(items, DEFAULT_PRICES)
    assert waste.retry.amount_usd > 0
    assert waste.dead.amount_usd > 0

    models = build_model_reports(items, DEFAULT_PRICES)
    assert {m.name for m in models} == {"model-alpha", "model-beta", "model-gamma"}

    out = render_report(overall=overall, models=models, waste=waste, out_path=OUT)
    html = out.read_text(encoding="utf-8")
    assert "CPAT" in html
    assert "HV score" in html  # the ranking table
    assert "model-gamma" in html
    assert "derived" in html  # waste estimates are labelled
    assert 'src="http' not in html and 'href="http' not in html  # self-contained
