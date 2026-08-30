"""One tick of the continuous grading loop, for scheduled runs.

    python -m handover.bench.continuous_run --state out/grade_state.json \
        --board out/grade_board.html --providers groq,openrouter --budget 1.00

Reads API keys from the environment (never files). Fetches the live catalog,
grades new/upgraded/due models on the verifiable seed tasks within a hard daily
budget, persists state, and re-renders the public board. Schedule it hourly
(cron / Windows Task Scheduler) and the index stays live. Content never leaves.
"""

import argparse
import os
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from handover.bench.board_page import render_board
from handover.bench.catalog import fetch_catalog
from handover.bench.continuous import tick
from handover.bench.discovery import CatalogModel
from handover.bench.runner import ModelSpec, run_model
from handover.bench.state_store import load_state, save_state
from handover.metrics.core import Proportion, proportion
from handover.replay.budget import DailyBudget
from handover.replay.openai_client import ENDPOINTS, HttpChatCaller

ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
}
# Fallback price per Mtok when a model isn't in the registry (in, out).
DEFAULT_PRICE = (Decimal("1"), Decimal("1"))

# HARD SAFETY: only providers with a genuine free tier may be graded by the
# scheduled loop. A paid provider is refused unless MEERADA_ALLOW_PAID=1 is set
# explicitly — the loop must never spend real money without a deliberate opt-in.
FREE_PROVIDERS = {"groq", "openrouter", "ollama"}

# Model ids that are not chat-completion models — skip these (audio/embed/etc).
_NON_CHAT = re.compile(r"whisper|tts|audio|embed|guard|moderation|rerank|orpheus|ocr", re.I)


def _is_chat_model(model_id: str) -> bool:
    return not _NON_CHAT.search(model_id)


def _keys(providers: list[str]) -> dict[str, str]:
    return {p: os.environ.get(ENV_KEYS.get(p, ""), "").strip() for p in providers}


def _overall_quality(per_cluster: dict[str, Proportion]) -> tuple[float | None, Proportion]:
    """Pool per-cluster success into one score (0-100) + pooled quality proportion."""
    total_s = sum(p.n * (p.value or 0) for p in per_cluster.values())
    total_n = sum(p.n for p in per_cluster.values())
    pooled = proportion(round(total_s), total_n) if total_n else proportion(0, 0)
    score = None if pooled.value is None else round(pooled.value * 100, 1)
    return score, pooled


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="handover.bench.continuous_run")
    parser.add_argument("--state", type=Path, default=Path("out/grade_state.json"))
    parser.add_argument("--board", type=Path, default=Path("out/grade_board.html"))
    parser.add_argument("--providers", default="groq,openrouter,deepseek,mistral,openai")
    parser.add_argument("--budget", type=Decimal, default=Decimal("1.00"))
    args = parser.parse_args(argv)

    providers = [p.strip() for p in args.providers.split(",") if p.strip() in ENDPOINTS]
    allow_paid = os.environ.get("MEERADA_ALLOW_PAID", "") == "1"
    if not allow_paid:
        blocked = [p for p in providers if p not in FREE_PROVIDERS]
        if blocked:
            print(f"safety: skipping paid providers {blocked} (set MEERADA_ALLOW_PAID=1 to allow)")
        providers = [p for p in providers if p in FREE_PROVIDERS]
    keys = _keys(providers)
    live = [p for p in providers if keys[p]]
    if not live:
        print("no free-tier providers with keys set — nothing to grade (no spend)")
        return 1

    state = load_state(args.state)
    budget = DailyBudget(args.budget)
    now = datetime.now(tz=UTC)

    def do_fetch() -> list[CatalogModel]:
        return [m for m in fetch_catalog(live, keys) if _is_chat_model(m.model_id)]

    callers = {p: HttpChatCaller(ENDPOINTS[p], keys[p]) for p in live}
    provider_of: dict[str, str] = {}

    def grade(model_id: str) -> tuple[float | None, Proportion]:
        provider = provider_of.get(model_id, live[0])
        caller = callers[provider]
        spec = ModelSpec(
            model_id=model_id,
            price_in_per_mtok=DEFAULT_PRICE[0],
            price_out_per_mtok=DEFAULT_PRICE[1],
        )

        def complete(system: str, user: str, max_tokens: int):  # type: ignore[no-untyped-def]
            return caller.complete(
                model_id, system, [{"role": "user", "content": user}], max_tokens
            )

        try:
            per_cluster = run_model(spec, complete, budget, repeats=3, delay_s=2.2)
        except Exception as exc:
            print(f"  skip {model_id}: {type(exc).__name__} {str(exc)[:80]}")
            return None, proportion(0, 0)
        quality = {c: m.success_rate for c, m in per_cluster.items()}
        return _overall_quality(quality)

    # Remember each model's provider for grading routing.
    for m in do_fetch():
        provider_of[m.model_id] = m.provider

    state, summary = tick(state, do_fetch, grade, budget, now)
    save_state(args.state, state)
    render_board(list(state.cards.values()), args.board, generated_at=now)

    print(f"tick @ {now:%Y-%m-%d %H:%MZ} | spent ${budget.spent_today():.4f}")
    print(
        f"graded: {len(summary.graded)} | prov: {summary.n_provisional} | "
        f"conf: {summary.n_confirmed}"
    )
    for change in summary.changes:
        if change.needs_grading:
            print(f"  {change.change}: {change.model_id}")
    print(f"board: {args.board.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
