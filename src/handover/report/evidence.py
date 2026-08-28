"""Evidence pack export (SPEC P3): a signed local bundle for auditors.

Contents: model inventory derived from actual traffic, the change-detection
log (drift alerts), and migration gap reports. Signed with the same per-file
sha256 manifest as the handover pack; nothing leaves the machine.
"""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from handover.canary.drift import DriftAlert
from handover.collect.redaction import assert_metadata_only
from handover.migrate.gap_report import GapReport
from handover.pack.builder import verify_signed_manifest, write_signed_manifest
from handover.schema.task import Task


def _guard_file(path: Path) -> None:
    """Refuse to emit an evidence file that looks like it carries content."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines() if path.suffix == ".jsonl" else [text]
    for line in lines:
        if line.strip():
            assert_metadata_only(json.loads(line), name=path.name)


def _inventory(tasks: Sequence[Task]) -> list[dict[str, object]]:
    by_model: dict[str, dict[str, int]] = {}
    for task in tasks:
        for model in task.models_used:
            entry = by_model.setdefault(model, {"n_tasks": 0, "n_verified": 0})
            entry["n_tasks"] += 1
            if task.verification_grade != "unknown":
                entry["n_verified"] += 1
    return [{"model_id": model, **counts} for model, counts in sorted(by_model.items())]


def export_evidence(
    out_dir: Path,
    *,
    tenant_id: UUID,
    period: str,
    tasks: Sequence[Task],
    drift_alerts: Sequence[DriftAlert] = (),
    gap_reports: Sequence[GapReport] = (),
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "inventory.json").write_text(
        json.dumps(_inventory(tasks), indent=2, sort_keys=True), encoding="utf-8"
    )
    # Structured alert fields only — no rendered prose. Every field is a number
    # or the already-sanitized cluster label, so the egress guard passes and a
    # consumer re-renders the §6.4 format from these fields.
    (out_dir / "change_log.jsonl").write_text(
        "\n".join(json.dumps(alert.model_dump(), sort_keys=True) for alert in drift_alerts),
        encoding="utf-8",
    )
    (out_dir / "gap_reports.json").write_text(
        json.dumps(
            [report.model_dump(mode="json") for report in gap_reports],
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    for name in ("inventory.json", "change_log.jsonl", "gap_reports.json"):
        _guard_file(out_dir / name)

    write_signed_manifest(
        out_dir,
        {
            "bundle": "evidence",
            "schema_version": "1.0",
            "created_at": datetime.now(tz=UTC).isoformat(),
            "tenant_id": str(tenant_id),
            "period": period,
            "n_tasks": len(tasks),
            "n_drift_alerts": len(drift_alerts),
            "n_gap_reports": len(gap_reports),
        },
    )
    return out_dir


def verify_evidence(out_dir: Path) -> list[str]:
    errors = [
        f"missing {name}"
        for name in ("inventory.json", "change_log.jsonl", "gap_reports.json")
        if not (out_dir / name).exists()
    ]
    return errors + verify_signed_manifest(out_dir)
