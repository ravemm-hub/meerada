"""``meerada crosscheck`` — ask several models, then let juries from the other
labs examine every answer. Keys come from the environment (OPENAI_API_KEY,
ANTHROPIC_API_KEY, GOOGLE_API_KEY, GROQ_API_KEY, ...); a model routes to the
provider that serves it. Nothing is stored unless ``--store`` is given.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from handover.copilot.router import _provider_of

crosscheck_app = typer.Typer(add_completion=False)


@crosscheck_app.callback(invoke_without_command=True)
def crosscheck(
    question: Annotated[str, typer.Argument(help="the task, in plain words")],
    models: Annotated[str, typer.Option("--models", help="comma-separated model ids to answer")],
    jurors: Annotated[
        str,
        typer.Option("--jurors", help="comma-separated juror pool (default: the answering models)"),
    ] = "",
    context: Annotated[
        str, typer.Option("--context", help="file whose content the answers must stay faithful to")
    ] = "",
    budget: Annotated[
        float, typer.Option("--budget", help="hard USD cap for the jury today")
    ] = 1.0,
    store: Annotated[
        str, typer.Option("--store", help="SQLite file to keep verdicts in (in-tenant)")
    ] = "",
    max_tokens: Annotated[int, typer.Option("--max-tokens")] = 700,
) -> None:
    """The model that examines models: same task to many, each answer judged by the other labs."""
    from handover.copilot.crosscheck import Answer, CrossCheck
    from handover.copilot.providers import caller_for_provider
    from handover.copilot.session import SessionManager
    from handover.replay.budget import DailyBudget
    from handover.replay.openai_client import ChatCaller

    ids = [m.strip() for m in models.split(",") if m.strip()]
    pool = [m.strip() for m in jurors.split(",") if m.strip()] or ids
    if not ids:
        typer.echo("no models given (use --models a,b,c)", err=True)
        raise typer.Exit(1)
    cache: dict[str, ChatCaller] = {}

    def caller_for(model_id: str) -> ChatCaller:
        provider = _provider_of(model_id)
        if provider not in cache:
            cache[provider] = caller_for_provider(provider)
        return cache[provider]

    try:
        manager = SessionManager(caller_for, max_tokens=max_tokens)
        replies = manager.fan_out(question, ids)
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    answers = [Answer(r.model_id, r.model_id, r.text) for r in replies if not r.error]
    for r in replies:
        typer.echo(
            f"== {r.model_id} ==\n  " + (f"error: {r.error}" if r.error else r.text.strip()[:500])
        )
    if not answers:
        typer.echo("no answers to examine", err=True)
        raise typer.Exit(1)
    saver = None
    if store:
        from handover.verify.jury_store import JuryStore

        saver = JuryStore(Path(store)).save
    ctx = Path(context).read_text(encoding="utf-8", errors="replace") if context else None
    checker = CrossCheck(caller_for, pool, DailyBudget(Decimal(str(budget))), store=saver)
    report = checker.examine(question, answers, context=ctx)
    typer.echo("")
    typer.echo(report.text)
