"""T11 + P1 acceptance: golden set rules, pack structure, validation, and the
end-to-end `hv pack` acceptance run on synthetic traffic."""

import json
from pathlib import Path
from uuid import uuid4

from handover.assemble import assemble_grouped
from handover.metrics.waste import TaskTraces
from handover.pack.builder import build_pack, validate_pack
from handover.pack.goldset import build_goldset
from tests.factories import make_trace, task_of
from tests.synthetic import generate_records


def test_goldset_only_measured_successes() -> None:
    items = [
        task_of(make_trace(start_s=0, status="pass")),  # measured pass -> eligible
        task_of(make_trace(start_s=400, status="fail")),  # fail -> out
        task_of(make_trace(start_s=800, status="unknown")),  # unknown -> out
    ]
    goldset = build_goldset("c01", items)
    assert len(goldset) == 1
    case = goldset[0]
    assert case.input_ref.startswith("trace://")
    assert case.expected_ref.endswith("/output")
    assert case.verifier_spec == "test_exit_code"


def test_goldset_size_rule_and_stratification() -> None:
    items = [
        task_of(
            make_trace(start_s=i * 400, status="pass", cost=f"{0.01 * (i + 1):.2f}", n_chars=i * 7)
        )
        for i in range(2000)
    ]
    goldset = build_goldset("c01", items)
    assert len(goldset) == 60  # max(30, 3% of 2000)
    costs = sorted(c.cost_usd for c in goldset)
    # Stratified: picks span the cheap and expensive ends, not one corner.
    assert costs[0] < costs[len(costs) // 2] < costs[-1]

    few = [task_of(make_trace(start_s=i * 400, status="pass")) for i in range(10)]
    assert len(build_goldset("c02", few)) == 10  # cannot invent cases


def test_goldset_never_inlines_content() -> None:
    items = [task_of(make_trace(start_s=0, status="pass"))]
    dumped = json.dumps([c.model_dump(mode="json") for c in build_goldset("c01", items)])
    assert "trace://" in dumped
    assert "content" not in dumped


def synthetic_items() -> list[TaskTraces]:
    grouped = assemble_grouped(generate_records(1500))
    return [TaskTraces(task=task, traces=traces) for task, traces in grouped]


def test_p1_acceptance_pack_from_traffic(tmp_path: Path) -> None:
    items = synthetic_items()
    pack_dir = build_pack(tmp_path / "pack", items, tenant_id=uuid4(), from_model="model-alpha")

    assert validate_pack(pack_dir) == []

    taxonomy = json.loads((pack_dir / "taxonomy.json").read_text(encoding="utf-8"))
    assert 8 <= len(taxonomy) <= 15

    largest = max(taxonomy, key=lambda c: c["n_tasks"])
    golden_lines = (
        (pack_dir / "golden" / f"{largest['cluster_id']}.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(golden_lines) >= 30

    contracts = json.loads((pack_dir / "contract.json").read_text(encoding="utf-8"))
    baselines = json.loads((pack_dir / "baseline.json").read_text(encoding="utf-8"))
    for entry in taxonomy:
        assert entry["cluster_id"] in contracts
        assert entry["cluster_id"] in baselines
        assert baselines[entry["cluster_id"]]["success_rate"]["n"] > 0

    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["n_clusters"] == len(taxonomy)

    # Tamper detection: corrupting a file must fail validation.
    (pack_dir / "taxonomy.json").write_text("[]", encoding="utf-8")
    assert any("digest mismatch" in e for e in validate_pack(pack_dir))


def test_validate_pack_missing_dir(tmp_path: Path) -> None:
    errors = validate_pack(tmp_path)
    assert any("missing manifest.json" in e for e in errors)
