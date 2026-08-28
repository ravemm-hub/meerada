"""T19 tests: routing recommendation logic, the receipt page, and the signed
evidence bundle with tamper detection."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from handover.branding import BRAND_NAME
from handover.canary.drift import DriftAlert
from handover.metrics import ModelPrice, TaskTraces, compute_core, compute_waste
from handover.report.evidence import export_evidence, verify_evidence
from handover.report.receipt import render_receipt, routing_recommendation
from handover.report.renderer import build_model_reports
from tests.factories import make_task, make_trace, task_of

PRICES = {"model-a": ModelPrice(input_per_mtok=Decimal("3"), output_per_mtok=Decimal("10"))}


def model_items(model: str, n: int, wins: int, cost: str) -> list[TaskTraces]:
    return [
        task_of(
            make_trace(
                start_s=i * 400, status="pass" if i < wins else "fail", model=model, cost=cost
            )
        )
        for i in range(n)
    ]


def reports(spender_cost: str = "0.50", cheap_wins: int = 95):
    items = model_items("expensive-model", 100, 90, spender_cost) + model_items(
        "cheap-model", 100, cheap_wins, "0.05"
    )
    return build_model_reports(items, PRICES), items


def test_recommendation_moves_to_better_value() -> None:
    models, _ = reports()
    rec = routing_recommendation(models)
    assert rec.kind == "move"
    assert rec.from_model == "expensive-model"
    assert rec.to_model == "cheap-model"
    assert rec.est_monthly_savings_usd is not None
    assert rec.est_monthly_savings_usd > Decimal("30")  # (0.556-0.053)*90 ≈ 45
    assert "estimate" in rec.note


def test_recommendation_stays_when_quality_drops_too_far() -> None:
    models, _ = reports(cheap_wins=70)  # 70% vs 90%: way past the 2pt guard
    rec = routing_recommendation(models)
    assert rec.kind == "stay"
    assert "quality" in rec.note


def test_recommendation_stays_with_single_model() -> None:
    models, _ = reports()
    rec = routing_recommendation(models[:1])
    assert rec.kind == "stay"


def test_receipt_renders(tmp_path: Path) -> None:
    models, items = reports()
    tasks = [item.task for item in items]
    out = render_receipt(
        period="2026-08",
        overall=compute_core(tasks),
        models=models,
        waste=compute_waste(items, PRICES),
        out_path=tmp_path / "receipt.html",
    )
    html = out.read_text(encoding="utf-8")
    assert f"{BRAND_NAME}" in html and "2026-08" in html
    assert "Delivered tasks" in html
    assert "expensive-model" in html and "cheap-model" in html
    assert "derived" in html and "measured" in html  # waste grades labelled
    assert "never routes" in html  # recommendation, not routing
    assert 'src="http' not in html and 'href="http' not in html


def make_alert() -> DriftAlert:
    return DriftAlert(
        model_id="model-x",
        cluster_id="c07",
        cluster_label="structured extraction",
        baseline_rate=0.91,
        current_rate=0.78,
        delta_points=-13.0,
        ci_low_points=-17.2,
        ci_high_points=-8.4,
        n=610,
        confirmed_windows=2,
        cusum_crossed=False,
        q_value=0.003,
        first_observed="2026-08-26 06:00Z",
    )


def test_evidence_bundle_signed_and_tamper_detected(tmp_path: Path) -> None:
    tasks = [make_task(model="model-a") for _ in range(5)] + [
        make_task(model="model-b", grade="unknown")
    ]
    bundle = export_evidence(
        tmp_path / "evidence",
        tenant_id=uuid4(),
        period="2026-08",
        tasks=tasks,
        drift_alerts=[make_alert()],
    )
    assert verify_evidence(bundle) == []

    import json

    inventory = json.loads((bundle / "inventory.json").read_text(encoding="utf-8"))
    by_model = {entry["model_id"]: entry for entry in inventory}
    assert by_model["model-a"]["n_tasks"] == 5
    assert by_model["model-b"]["n_verified"] == 0

    change_log = (bundle / "change_log.jsonl").read_text(encoding="utf-8")
    assert "structured extraction" in change_log  # sanitized label only
    assert '"baseline_rate": 0.91' in change_log  # structured fields, no prose
    assert "pass rate:" not in change_log  # rendered prose removed (leak channel closed)

    (bundle / "inventory.json").write_text("[]", encoding="utf-8")
    assert any("digest mismatch" in e for e in verify_evidence(bundle))


def test_evidence_verify_missing_files(tmp_path: Path) -> None:
    errors = verify_evidence(tmp_path)
    assert any("missing inventory.json" in e for e in errors)


def test_receipt_generated_at_is_stable_when_injected(tmp_path: Path) -> None:
    models, items = reports()
    tasks = [item.task for item in items]
    fixed = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    out = render_receipt(
        period="2026-08",
        overall=compute_core(tasks),
        models=models,
        waste=compute_waste(items, PRICES),
        out_path=tmp_path / "r.html",
        generated_at=fixed,
    )
    assert "2026-08-31 12:00Z" in out.read_text(encoding="utf-8")
