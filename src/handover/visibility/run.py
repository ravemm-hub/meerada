"""One tick of the Visibility Monitor (the daily workflow runs this):

    python -m handover.visibility.run --state visibility_state.json \
        --out out/visibility.html --json out/visibility.json \
        --engines chatgpt,perplexity,gemini,claude --per-tick 13 --budget 0.60

Each engine gets the ``--per-tick`` questions it has gone longest without; every
call is pre-authorized against the hard daily cap and stops when it would exceed
it. State is saved after every answer, so a crash loses nothing.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from handover.replay.budget import DailyBudget
from handover.visibility.engines import Engine, EngineError, engines_from_env
from handover.visibility.experiments import load_experiments
from handover.visibility.extract import extract_mentions
from handover.visibility.features import answer_features
from handover.visibility.page import render_page
from handover.visibility.questions import BY_ID, QUESTIONS, Query
from handover.visibility.report import build_report
from handover.visibility.state import Answer, State, load_state, pick_queries, save_state


def ask_one(engine: Engine, query: Query, now: datetime) -> Answer:
    started = time.perf_counter()
    try:
        reply = engine.ask(query.text)
    except EngineError as exc:
        return Answer(
            engine=engine.name,
            model=engine.model,
            query_id=query.id,
            asked_at=now,
            text="",
            error=str(exc)[:400],
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    mentions = extract_mentions(
        reply.text, exclude=(query.city, query.category), citations=reply.citations
    )
    return Answer(
        engine=engine.name,
        model=reply.model or engine.model,
        query_id=query.id,
        asked_at=now,
        text=reply.text,
        citations=reply.citations,
        names=[m.name for m in mentions],
        name_keys=[m.key for m in mentions],
        features=answer_features(reply.text, reply.citations, [m.name for m in mentions]),
        latency_ms=int((time.perf_counter() - started) * 1000),
        cost_usd=str(engine.estimate_usd),  # declared: the per-call estimate, not a bill
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        searches=reply.searches,
    )


def tick(
    state: State,
    engines: list[Engine],
    budget: DailyBudget,
    per_tick: int,
    now: datetime,
    queries: tuple[Query, ...] = QUESTIONS,
    save: Path | None = None,
    runs: int = 1,
) -> list[Answer]:
    """Ask, record, save; returns what this tick added. ``runs`` > 1 repeats every
    question (test-case rounds: the engines are volatile, one answer proves nothing)."""
    added: list[Answer] = []
    for engine in engines:
        for query in pick_queries(state, engine.name, queries, per_tick):
            for _ in range(max(1, runs)):
                if not budget.can_spend(engine.estimate_usd):
                    print(f"budget: skipping {engine.name} {query.id}", file=sys.stderr)
                    break
                answer = ask_one(engine, query, now)
                budget.record(Decimal(answer.cost_usd) if not answer.error else Decimal("0"))
                state.add(answer)
                added.append(answer)
                if save is not None:
                    save_state(state, save)
    return added


def reextract(state: State) -> int:
    """Re-read every stored answer with the current extractor — names are derived
    from the verbatim text, so a better reader improves the history too."""
    count = 0
    for a in state.answers:
        if a.error:
            continue
        q = BY_ID.get(a.query_id)
        exclude = (q.city, q.category) if q else ()
        mentions = extract_mentions(a.text, exclude=exclude, citations=a.citations)
        a.names, a.name_keys = [m.name for m in mentions], [m.key for m in mentions]
        a.features = answer_features(a.text, a.citations, a.names)
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visibility Monitor — one tick")
    parser.add_argument("--state", type=Path, default=Path("visibility_state.json"))
    parser.add_argument("--out", type=Path, default=Path("out/visibility.html"))
    parser.add_argument("--json", type=Path, default=Path("out/visibility.json"))
    parser.add_argument("--engines", default="chatgpt,perplexity,gemini,claude")
    parser.add_argument("--per-tick", type=int, default=13)
    parser.add_argument("--budget", type=Decimal, default=Decimal("0.60"))
    parser.add_argument("--only", default="", help="comma-separated query ids (smoke runs)")
    parser.add_argument(
        "--runs", type=int, default=1, help="repeat each question this many times (test cases)"
    )
    parser.add_argument("--cases", type=Path, default=None, help="also write the test-case page")
    parser.add_argument("--report-only", action="store_true", help="re-render, ask nothing")
    parser.add_argument(
        "--experiments",
        type=Path,
        default=Path("data/experiments.json"),
        help="registry of controlled experiments (business, lever, questions, start)",
    )
    parser.add_argument(
        "--reextract", action="store_true", help="re-read stored answers with the current extractor"
    )
    args = parser.parse_args(argv)

    names = [n.strip() for n in args.engines.split(",") if n.strip()]
    state = load_state(args.state)
    now = datetime.now(tz=UTC)
    queries: tuple[Query, ...] = QUESTIONS
    if args.only:
        wanted = {q.strip() for q in args.only.split(",")}
        queries = tuple(q for q in QUESTIONS if q.id in wanted)

    if not args.report_only:
        engines, skipped = engines_from_env(names)
        state.skipped = skipped
        for name, why in skipped.items():
            print(f"skip {name}: {why}", file=sys.stderr)
        budget = DailyBudget(args.budget)
        added = tick(
            state, engines, budget, args.per_tick, now, queries, save=args.state, runs=args.runs
        )
        errors = sum(1 for a in added if a.error)
        print(
            f"tick @ {now:%Y-%m-%d %H:%MZ} | asked {len(added)} ({errors} errors)"
            f" | est. spend ${budget.spent_today():.4f} of ${args.budget}"
        )
        save_state(state, args.state)

    if args.reextract:
        print(f"re-extracted {reextract(state)} answers")
        save_state(state, args.state)

    report = build_report(state, QUESTIONS, names, now, load_experiments(args.experiments))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(_dumps(report), encoding="utf-8")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_page(report), encoding="utf-8")
    if args.cases is not None:
        from handover.visibility.cases import render_cases

        args.cases.parent.mkdir(parents=True, exist_ok=True)
        args.cases.write_text(render_cases(report), encoding="utf-8")
    print(f"wrote {args.out} and {args.json}")
    return 0


def _dumps(report: dict[str, object]) -> str:
    import json

    return json.dumps(report, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    raise SystemExit(main())
