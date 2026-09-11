"""``meerada guard`` — the watchdog + cage as a standalone command.

* ``meerada guard``          watch live Claude Code sessions, alert on the desktop
* ``meerada guard policy``   print the effective policy and where it came from
* ``meerada guard check``    run the cage on a file or stdin (CI / pre-commit use)
* ``meerada guard init``     write a starter ~/.meerada/guard.toml (or --company)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

guard_app = typer.Typer(no_args_is_help=False, add_completion=False, invoke_without_command=True)

_STARTER = """# Meerada Guard policy — https://meerada.app/guard.html
enabled = true

# stall / burn
silence_s = 120            # no output for this long = silent
max_repeat = 3             # same tool call this many times = loop
session_budget_usd = 5.0   # hard cap per task (0 = off)
daily_budget_usd = 25.0    # hard cap per day (0 = off)
action = "alert"           # alert | stop

# cage
cage = true
allowed_roots = []         # workspace roots; empty = the current directory
allowed_hosts = []         # hosts a model may reach; empty = warn on every outbound host
block_secrets = true
cage_action = "warn"       # warn | block

# company (optional)
webhook_url = ""           # Slack / Teams incoming webhook: every alert lands there
locked = []                # in a machine policy: fields users may not override
"""


@guard_app.callback()
def watch(
    ctx: typer.Context,
    interval: Annotated[float, typer.Option("--interval", help="seconds between checks")] = 2.0,
    no_desktop: Annotated[bool, typer.Option("--no-desktop", help="console only")] = False,
) -> None:
    """Watch live Claude Code sessions; alert when a task stalls, burns or reaches out."""
    if ctx.invoked_subcommand is not None:
        return
    from handover.guard.alerts import default_sinks
    from handover.guard.claude_watch import ClaudeCodeWatcher
    from handover.guard.policy import load_policy, policy_text

    policy = load_policy()
    typer.echo(
        "Meerada Guard — watching ~/.claude/projects (Ctrl+C to stop)\n" + policy_text(policy)
    )
    _ring, sink = default_sinks(policy.webhook_url, desktop=not no_desktop)
    watcher = ClaudeCodeWatcher(policy, sink)
    try:
        watcher.run(interval_s=interval)
    except KeyboardInterrupt:
        typer.echo("guard stopped")


@guard_app.command()
def policy() -> None:
    """Show the effective policy (defaults < user < company < MEERADA_GUARD_POLICY)."""
    from handover.guard.policy import load_policy, policy_text

    typer.echo(policy_text(load_policy()))


@guard_app.command()
def check(
    path: Annotated[str, typer.Argument(help="file to inspect, or - for stdin")] = "-",
) -> None:
    """Run the cage on text: secrets, paths outside the workspace, outbound network."""
    from handover.guard.cage import decision, inspect_outbound
    from handover.guard.policy import load_policy

    text = (
        sys.stdin.read()
        if path == "-"
        else Path(path).read_text(encoding="utf-8", errors="replace")
    )
    findings = inspect_outbound(text, load_policy())
    for f in findings:
        typer.echo(f"{f.severity.upper():5} {f.kind:18} {f.what} — {f.snippet}")
    verdict = decision(findings)
    typer.echo(f"verdict: {verdict}")
    raise typer.Exit(code=2 if verdict == "block" else 0)


@guard_app.command()
def init(
    company: Annotated[
        bool, typer.Option("--company", help="write the machine-wide policy")
    ] = False,
) -> None:
    """Write a starter policy file you can edit."""
    from handover.guard.policy import USER_FILE, machine_policy_path

    target = machine_policy_path() if company else USER_FILE
    if target.exists():
        typer.echo(f"exists: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_STARTER, encoding="utf-8")
    typer.echo(f"wrote {target}")
