"""The free developer CLI: ``meerada record``, ``meerada report``, ``meerada pack`` (alias: ``hv``).

Runs entirely locally against SQLite — zero infrastructure. This is the
distribution wedge: a developer records a trace source and gets the ranked
CPAT report in two commands.
"""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from handover.assemble import AttemptRecord, assemble_grouped
from handover.branding import CLI_NAME
from handover.cli.store import SqliteStore
from handover.collect import Normalizer, RawEvent
from handover.metrics import TaskTraces, compute_core, compute_waste
from handover.pack.builder import build_pack, validate_pack
from handover.report.__main__ import DEFAULT_PRICES
from handover.report.renderer import build_model_reports, render_report


def _force_utf8() -> None:
    """Windows consoles default to a legacy codepage (cp1255 here); force UTF-8
    so report paths and status glyphs never crash the CLI."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


_force_utf8()

app = typer.Typer(no_args_is_help=True, add_completion=False)

DbOption = Annotated[Path, typer.Option("--db", help="SQLite database path")]
DEFAULT_DB = Path(f"{CLI_NAME}.db")
DEFAULT_REPORT = Path(f"{CLI_NAME}-report.html")


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
    out: Annotated[Path, typer.Option("--out", help="output HTML path")] = DEFAULT_REPORT,
) -> None:
    """Assemble tasks, compute CPAT and waste, render the ranked HTML report."""
    if not db.exists():
        typer.echo(f"no database at {db} — run `{CLI_NAME} record` first", err=True)
        raise typer.Exit(1)
    store = SqliteStore(db)
    stored = store.load_records()
    store.close()
    if not stored:
        typer.echo(f"store is empty — run `{CLI_NAME} record` first", err=True)
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
        f"tasks: {overall.n_tasks} ({overall.n_verified} verified) | unknown-rate: {unknown}",
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
        typer.echo(f"no database at {db} — run `{CLI_NAME} record` first", err=True)
        raise typer.Exit(1)
    store = SqliteStore(db)
    stored = store.load_records()
    tenant = store.tenant_id()
    store.close()
    if not stored:
        typer.echo(f"store is empty — run `{CLI_NAME} record` first", err=True)
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
        f"clusters: {manifest['n_clusters']} | tasks: {manifest['n_tasks']} | "
        f"from-model: {manifest['from_model']} | valid OK"
    )


@app.command()
def ask(
    intent: Annotated[str, typer.Argument(help="what you want, in plain words")],
    model: Annotated[str, typer.Option("--model", help="model id")] = "llama-3.1-8b-instant",
    provider: Annotated[str, typer.Option("--provider", help="free-tier provider")] = "groq",
    max_tokens: Annotated[int, typer.Option("--max-tokens")] = 512,
) -> None:
    """Copilot: rewrite your intent into a lean prompt and send it to one model."""
    from handover.copilot.optimize import optimize
    from handover.copilot.providers import caller_for_provider

    opt = optimize(intent, model)
    typer.echo(f"translated ({opt.saved_pct}% fewer tokens than a naive prompt)")
    typer.echo(f"  system: {opt.system}")
    typer.echo(f"  user:   {opt.user}")
    try:
        caller = caller_for_provider(provider)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    completion = caller.complete(
        model, opt.system, [{"role": "user", "content": opt.user}], max_tokens
    )
    typer.echo("---")
    typer.echo(completion.text)
    typer.echo(f"[{completion.input_tokens} in / {completion.output_tokens} out tokens]")


@app.command()
def fan(
    intent: Annotated[str, typer.Argument(help="what you want, in plain words")],
    models: Annotated[str, typer.Option("--models", help="comma-separated model ids")],
    provider: Annotated[str, typer.Option("--provider", help="free-tier provider")] = "groq",
    max_tokens: Annotated[int, typer.Option("--max-tokens")] = 512,
) -> None:
    """Copilot: run the same intent across several models in parallel, one cockpit."""
    from handover.copilot.providers import caller_for_provider
    from handover.copilot.session import SessionManager

    ids = [m.strip() for m in models.split(",") if m.strip()]
    if not ids:
        typer.echo("no models given (use --models a,b,c)", err=True)
        raise typer.Exit(1)
    try:
        caller = caller_for_provider(provider)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    manager = SessionManager(lambda _model_id: caller, max_tokens=max_tokens)
    for reply in manager.fan_out(intent, ids):
        typer.echo(f"== {reply.model_id}  ({reply.prompt.saved_pct}% fewer tokens) ==")
        if reply.error:
            typer.echo(f"  error: {reply.error}")
        else:
            typer.echo(f"  {reply.text.strip()[:600]}")


@app.command()
def up(
    port: Annotated[int, typer.Option("--port", help="localhost port")] = 8765,
    provider: Annotated[str, typer.Option("--provider", help="free-tier provider")] = "groq",
    no_open: Annotated[bool, typer.Option("--no-open", help="don't open the browser")] = False,
) -> None:
    """Open LLManager in your browser — many models, one place, parallel."""
    from handover.copilot.serve import serve

    typer.echo(f"Meerada LLManager on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    serve(port=port, provider=provider, open_browser=not no_open)


@app.command("app")
def desktop_app(
    port: Annotated[int, typer.Option("--port", help="localhost port (0 = auto)")] = 0,
) -> None:
    """Open Meerada LLManager as a desktop app — native window, your own keys, local."""
    from handover.copilot.desktop import run

    typer.echo("Meerada LLManager (desktop) — your keys stay on this machine. Ctrl+C to quit.")
    run(port=port or None)


if __name__ == "__main__":
    app()
