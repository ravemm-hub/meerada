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


@visibility_app.command("audit")
def audit_cmd(
    url: Annotated[str, typer.Argument(help="the business website")],
    name: Annotated[str, typer.Option("--name", help="business name as on Google/Yelp")] = "",
    as_json: Annotated[bool, typer.Option("--json", help="print JSON instead of text")] = False,
) -> None:
    """Entity audit v0: can the engines read this site, and what is missing (declared)."""
    import json

    from handover.visibility.audit import audit, format_audit

    result = audit(url, name)
    typer.echo(
        json.dumps(result.as_dict(), ensure_ascii=False, indent=1)
        if as_json
        else format_audit(result)
    )


@visibility_app.command("guides")
def guides_cmd(
    data: Annotated[str, typer.Option("--data")] = "data/guides",
    out: Annotated[str, typer.Option("--out")] = "site/guides",
) -> None:
    """Build the editorial guide pages from data/guides/*.json."""
    from pathlib import Path

    from handover.visibility.guides import build_guides

    for path in build_guides(Path(data), Path(out)):
        typer.echo(f"wrote {path}")


@visibility_app.command("profiles")
def profiles_cmd(
    data: Annotated[str, typer.Option("--data")] = "data/profiles",
    out: Annotated[str, typer.Option("--out")] = "site/b",
) -> None:
    """Build the factual profile pages from data/profiles/*.json."""
    from pathlib import Path

    from handover.visibility.profiles import build_profiles

    for path in build_profiles(Path(data), Path(out)):
        typer.echo(f"wrote {path}")


@visibility_app.command("pages")
def pages_cmd(
    state: Annotated[str, typer.Option("--state")] = "visibility_state.json",
    out: Annotated[str, typer.Option("--out")] = "site/s",
) -> None:
    """Build the static 'what the AI shows' page for every measured question."""
    from pathlib import Path

    from handover.visibility.pages import build_query_pages
    from handover.visibility.state import load_state

    written = build_query_pages(load_state(Path(state)), Path(out))
    typer.echo(f"wrote {len(written)} files to {out}")


@visibility_app.command("gap")
def gap_cmd(
    state: Annotated[str, typer.Option("--state")] = "visibility_state.json",
    out: Annotated[str, typer.Option("--out")] = "site/gap",
) -> None:
    """Build the public gap page for every business Google lists that the engines rarely name."""
    from pathlib import Path

    from handover.visibility.gap import build_gap_pages
    from handover.visibility.state import load_state

    written = build_gap_pages(load_state(Path(state)), Path(out))
    typer.echo(f"wrote {len(written)} files to {out}")


@visibility_app.command("outreach")
def outreach_cmd(
    experiments: Annotated[str, typer.Option("--experiments")] = "data/experiments.json",
    state: Annotated[str, typer.Option("--state")] = "visibility_state.json",
    out: Annotated[str, typer.Option("--out")] = "out/outreach",
    leads: Annotated[str, typer.Option("--leads")] = "site/gap/leads.json",
) -> None:
    """Write the pilot outreach drafts (EN + HE) for the founder to review. Sends nothing."""
    from pathlib import Path

    from handover.visibility.outreach import build_outreach
    from handover.visibility.state import load_state

    written = build_outreach(Path(experiments), load_state(Path(state)), Path(out), Path(leads))
    typer.echo(f"wrote {len(written)} drafts to {out}")
