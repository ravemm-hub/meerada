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


@visibility_app.command("pilots")
def pilots_cmd(
    experiments: Annotated[str, typer.Option("--experiments")] = "data/experiments.json",
    state: Annotated[str, typer.Option("--state")] = "visibility_state.json",
    out: Annotated[str, typer.Option("--out")] = "out/pilots",
) -> None:
    """Weekly proof for every pilot: numbers vs baseline, a digest, and EN+HE report drafts."""
    from pathlib import Path

    from handover.visibility.pilots import build_pilot_reports
    from handover.visibility.state import load_state

    written = build_pilot_reports(Path(experiments), load_state(Path(state)), Path(out))
    typer.echo(f"wrote {len(written)} files to {out}")


@visibility_app.command("profile-draft")
def profile_draft_cmd(
    url: str,
    name: Annotated[str, typer.Option("--name")] = "",
    city: Annotated[str, typer.Option("--city")] = "",
    category: Annotated[str, typer.Option("--category")] = "",
    out: Annotated[str, typer.Option("--out")] = "data/profiles/drafts",
) -> None:
    """Draft a factual profile from a business website — every field marked to confirm."""
    from pathlib import Path

    from handover.visibility.profile_draft import draft_profile, write_draft

    path = write_draft(draft_profile(url, name, city, category), Path(out))
    typer.echo(f"wrote {path}")


@visibility_app.command("claims")
def claims_cmd(
    token_file: Annotated[str, typer.Option("--token-file")] = "",
    pilots: Annotated[str, typer.Option("--pilots")] = "data/pilots.json",
    contacts: Annotated[str, typer.Option("--contacts")] = "out/claims/claims.json",
) -> None:
    """Pull new claims from Supabase into pilots; contact details stay out of git."""
    import os
    from pathlib import Path

    from handover.visibility.claims import fetch_claims, intake, last_claim_id

    token = (
        Path(token_file).read_text(encoding="utf-8").strip()
        if token_file
        else os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    )
    if not token:
        raise typer.BadParameter("need --token-file or SUPABASE_ACCESS_TOKEN")
    rows = fetch_claims(token, after=last_claim_id(Path(contacts)))
    new_claims, new_pilots = intake(rows, Path(pilots), Path(contacts))
    typer.echo(f"{len(rows)} rows read, {len(new_claims)} new claims, {len(new_pilots)} new pilots")
    for p in new_pilots:
        typer.echo(
            f"  pilot {p['id']}: {p['business']} → {p['queries'][0]} (contact in {contacts})"
        )
    for c in new_claims:
        if not any(p["business"] == (c.get("business") or "").strip() for p in new_pilots):
            typer.echo(f"  no measured question for claim {c['id']}: {c.get('query', '')[:60]!r}")


@visibility_app.command("home")
def home_cmd(
    pages: Annotated[str, typer.Option("--pages")] = "site/s",
    out: Annotated[str, typer.Option("--out")] = "site/index.html",
) -> None:
    """Build the home page: Google vs the AI engines per question, the checker, the offer."""
    from pathlib import Path

    from handover.visibility.home import build_home

    typer.echo(f"wrote {build_home(Path(pages), Path(out))}")


@visibility_app.command("fixkit")
def fixkit_cmd(
    experiments: Annotated[str, typer.Option("--experiments")] = "data/experiments.json",
    state: Annotated[str, typer.Option("--state")] = "visibility_state.json",
    out: Annotated[str, typer.Option("--out")] = "out/pilots",
) -> None:
    """Write each pilot's fix-kit file: instructions its owner hands to Claude or a developer."""
    from pathlib import Path

    from handover.visibility.fixkit import write_fixkits
    from handover.visibility.state import load_state

    for path in write_fixkits(Path(experiments), load_state(Path(state)), Path(out)):
        typer.echo(f"wrote {path}")
