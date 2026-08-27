"""The free developer CLI: ``hv record``, ``hv report``, ``hv pack``.

Runs entirely locally against SQLite — zero infrastructure. This is the
distribution wedge: a developer records a trace source and gets the ranked
CPAT report in two commands.
"""

import json
from pathlib import Path
from typing import Annotated

import typer

from handover.assemble import AttemptRecord, assemble_grouped
from handover.cli.store import SqliteStore
from handover.collect import Normalizer, RawEvent
from handover.metrics import TaskTraces, compute_core, compute_waste
from handover.pack.builder import build_pack, validate_pack
from handover.report.__main__ import DEFAULT_PRICES
from handover.report.renderer import build_model_reports, render_report

app = typer.Typer(no_args_is_help=True, add_completion=False)

DbOption = Annotated[Path, typer.Option("--db", help="SQLite database path")]
DEFAULT_DB = Path("hv.db")


@app.command()
def record(
    source: Annotated[Path, typer.Argument(help="JSONL file of raw events (in-tenant)")],
    db: DbOption = DEFAULT_DB,
) -> None:
    """Ingest a trace source: normalize raw events into metadata-only traces."""
    if not source.exists():
        typer.echo(f"source not found: {source}", err=True)
        raise typer.Exit(1)
    store = SqliteStore(db)
    normalizer = Normalizer(tenant_id=store.tenant_id(), salt=store.salt())
    records: list[AttemptRecord] = []
    skipped = 0
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = RawEvent.model_validate_json(line)
        except ValueError:
            skipped += 1
            continue
        records.append(
            AttemptRecord(
                trace=normalizer.normalize(raw),
                session_id=raw.session_id,
                explicit_task_id=raw.task_id,
            )
        )
    added = store.add_records(records)
    typer.echo(f"recorded {added} traces ({skipped} malformed lines skipped) -> {db}")
    typer.echo(f"total in store: {store.count()}")
    store.close()


@app.command()
def report(
    db: DbOption = DEFAULT_DB,
    out: Annotated[Path, typer.Option("--out", help="output HTML path")] = Path("hv-report.html"),
) -> None:
    """Assemble tasks, compute CPAT and waste, render the ranked HTML report."""
    if not db.exists():
        typer.echo(f"no database at {db} — run `hv record` first", err=True)
        raise typer.Exit(1)
    store = SqliteStore(db)
    stored = store.load_records()
    store.close()
    if not stored:
        typer.echo("store is empty — run `hv record` first", err=True)
        raise typer.Exit(1)

    grouped = assemble_grouped(stored)
    tasks = [task for task, _ in grouped]
    items = [TaskTraces(task=task, traces=traces) for task, traces in grouped]
    overall = compute_core(tasks)
    path = render_report(
        overall=overall,
        models=build_model_reports(items, DEFAULT_PRICES),
        waste=compute_waste(items, DEFAULT_PRICES),
        out_path=out,
    )
    unknown = "—" if overall.unknown_rate.value is None else f"{overall.unknown_rate.value:.1%}"
    typer.echo(f"report: {path.resolve()}")
    typer.echo(
        f"tasks: {overall.n_tasks} ({overall.n_verified} verified) · unknown-rate: {unknown}"
    )
    if (overall.unknown_rate.value or 0) > 0.30:
        typer.echo(
            "warning: unknown-rate above 30% — add verification signals "
            "(exit codes, schemas) to make the numbers meaningful",
            err=True,
        )


@app.command()
def pack(
    db: DbOption = DEFAULT_DB,
    out: Annotated[Path, typer.Option("--out", help="pack output directory")] = Path(
        "handover-pack"
    ),
) -> None:
    """Build a handover pack: taxonomy, contracts, tool policies, golden sets."""
    if not db.exists():
        typer.echo(f"no database at {db} — run `hv record` first", err=True)
        raise typer.Exit(1)
    store = SqliteStore(db)
    stored = store.load_records()
    tenant = store.tenant_id()
    store.close()
    if not stored:
        typer.echo("store is empty — run `hv record` first", err=True)
        raise typer.Exit(1)

    grouped = assemble_grouped(stored)
    items = [TaskTraces(task=task, traces=traces) for task, traces in grouped]
    from_model = max(
        (task.models_used[-1] for task, _ in grouped),
        key=[task.models_used[-1] for task, _ in grouped].count,
    )
    pack_dir = build_pack(out, items, tenant_id=tenant, from_model=from_model)
    errors = validate_pack(pack_dir)
    if errors:
        for error in errors:
            typer.echo(f"invalid pack: {error}", err=True)
        raise typer.Exit(1)
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    typer.echo(f"pack: {pack_dir.resolve()}")
    typer.echo(
        f"clusters: {manifest['n_clusters']} · tasks: {manifest['n_tasks']} · "
        f"from-model: {manifest['from_model']} · valid ✓"
    )


if __name__ == "__main__":
    app()
