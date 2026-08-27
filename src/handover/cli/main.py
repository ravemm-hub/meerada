"""The free developer CLI: ``hv record``, ``hv report``, ``hv pack``.

Runs entirely locally against SQLite — zero infrastructure. This is the
distribution wedge: a developer records a trace source and gets the ranked
CPAT report in two commands.
"""

from pathlib import Path
from typing import Annotated

import typer

from handover.assemble import AttemptRecord, assemble_grouped
from handover.cli.store import SqliteStore
from handover.collect import Normalizer, RawEvent
from handover.metrics import TaskTraces, compute_core, compute_waste
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
def pack(db: DbOption = DEFAULT_DB) -> None:
    """Build a handover pack (taxonomy, contracts, golden set). Arrives in P1."""
    typer.echo(
        "`hv pack` requires cluster extraction (P1: T9-T11) which is not built yet.", err=True
    )
    raise typer.Exit(2)


if __name__ == "__main__":
    app()
