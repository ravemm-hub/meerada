"""``meerada visibility`` — who do the AI answer engines recommend for everyday
local needs? Keys from the environment; spend under a hard daily cap."""

from __future__ import annotations

from typing import Annotated

import typer

visibility_app = typer.Typer(add_completion=False, no_args_is_help=True)


@visibility_app.command("run")
def run(
    state: Annotated[str, typer.Option("--state", help="answers JSON (kept verbatim)")] = (
        "visibility_state.json"
    ),
    out: Annotated[str, typer.Option("--out", help="HTML page to write")] = "out/visibility.html",
    json_out: Annotated[str, typer.Option("--json", help="JSON report to write")] = (
        "out/visibility.json"
    ),
    engines: Annotated[str, typer.Option("--engines")] = "chatgpt,perplexity,gemini,claude",
    per_tick: Annotated[int, typer.Option("--per-tick", help="questions per engine")] = 13,
    budget: Annotated[float, typer.Option("--budget", help="hard USD cap for today")] = 0.60,
    only: Annotated[str, typer.Option("--only", help="comma-separated query ids")] = "",
) -> None:
    """Ask the engines one round of questions, then rebuild the page."""
    from handover.visibility.run import main

    argv = [
        "--state",
        state,
        "--out",
        out,
        "--json",
        json_out,
        "--engines",
        engines,
        "--per-tick",
        str(per_tick),
        "--budget",
        str(budget),
    ]
    if only:
        argv += ["--only", only]
    raise typer.Exit(main(argv))


@visibility_app.command("report")
def report(
    state: Annotated[str, typer.Option("--state")] = "visibility_state.json",
    out: Annotated[str, typer.Option("--out")] = "out/visibility.html",
    json_out: Annotated[str, typer.Option("--json")] = "out/visibility.json",
    engines: Annotated[str, typer.Option("--engines")] = "chatgpt,perplexity,gemini,claude",
) -> None:
    """Rebuild the page from the stored answers without asking anything."""
    from handover.visibility.run import main

    argv = [
        "--state",
        state,
        "--out",
        out,
        "--json",
        json_out,
        "--engines",
        engines,
        "--report-only",
    ]
    raise typer.Exit(main(argv))
