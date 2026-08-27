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
from handover.migrate.gap_report import GapReport
from handover.pack.builder import verify_signed_manifest, write_signed_manifest
from handover.schema.task import Task


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
    (out_dir / "change_log.jsonl").write_text(
        "\n".join(
            json.dumps({**alert.model_dump(), "rendered": alert.render()}, sort_keys=True)
            for alert in drift_alerts
        ),
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
