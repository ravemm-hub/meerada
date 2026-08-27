"""CLI entry: python -m handover.report --fixtures tests/fixtures --out out/report.html

Reads raw-event JSONL files, runs the full local pipeline (normalize -> assemble
-> metrics -> waste), and renders the self-contained HTML report.
"""

import argparse
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from handover.assemble import AttemptRecord, assemble_grouped
from handover.collect import Normalizer, RawEvent
from handover.metrics import ModelPrice, TaskTraces, by_model, compute_core, compute_waste
from handover.report.renderer import render_report

# P0 price table; replaced by the model_registry table in P1+.
DEFAULT_PRICES: dict[str, ModelPrice] = {
    "claude-sonnet-4-6": ModelPrice(input_per_mtok=Decimal("3"), output_per_mtok=Decimal("15")),
    "gpt-5": ModelPrice(input_per_mtok=Decimal("1.25"), output_per_mtok=Decimal("10")),
    "model-alpha": ModelPrice(input_per_mtok=Decimal("3"), output_per_mtok=Decimal("15")),
    "model-beta": ModelPrice(input_per_mtok=Decimal("1.1"), output_per_mtok=Decimal("4.4")),
    "model-gamma": ModelPrice(input_per_mtok=Decimal("0.3"), output_per_mtok=Decimal("1.2")),
}


def load_records(path: Path, normalizer: Normalizer) -> list[AttemptRecord]:
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    records: list[AttemptRecord] = []
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = RawEvent.model_validate_json(line)
            records.append(
                AttemptRecord(
                    trace=normalizer.normalize(raw),
                    session_id=raw.session_id,
                    explicit_task_id=raw.task_id,
                )
            )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="handover.report")
    parser.add_argument("--fixtures", type=Path, required=True, help="JSONL file or directory")
    parser.add_argument("--out", type=Path, required=True, help="output HTML path")
    parser.add_argument("--salt", default="local-dev-salt")
    args = parser.parse_args(argv)

    normalizer = Normalizer(tenant_id=UUID(int=0), salt=args.salt)
    grouped = assemble_grouped(load_records(args.fixtures, normalizer))
    tasks = [task for task, _ in grouped]
    overall = compute_core(tasks)
    waste = compute_waste(
        [TaskTraces(task=task, traces=traces) for task, traces in grouped], DEFAULT_PRICES
    )
    out = render_report(overall=overall, per_model=by_model(tasks), waste=waste, out_path=args.out)
    unknown = "—" if overall.unknown_rate.value is None else f"{overall.unknown_rate.value:.1%}"
    print(f"report: {out}")
    print(f"tasks: {overall.n_tasks} ({overall.n_verified} verified) · unknown-rate: {unknown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
