"""Run the public Meerada Grade index against live models.

    python -m handover.bench --providers groq,openrouter --out out/index.html

Reads API keys from the environment (never from files): OPENAI_API_KEY,
GROQ_API_KEY, OPENROUTER_API_KEY, DEEPSEEK_API_KEY, MISTRAL_API_KEY. Only
providers with a key present are run. A hard daily budget caps spend.
"""

import argparse
import os
from decimal import Decimal
from pathlib import Path

from handover.bench.runner import ModelSpec, run_index
from handover.metrics.index import compute_index
from handover.replay.budget import DailyBudget
from handover.replay.openai_client import ENDPOINTS, HttpChatCaller
from handover.report.index_page import render_index

# provider -> (env var, [(model_id, price_in, price_out)]) — from the landscape research.
CATALOG: dict[str, tuple[str, list[tuple[str, str, str]]]] = {
    "groq": ("GROQ_API_KEY", [("llama-3.3-70b-versatile", "0.59", "0.79")]),
    "openrouter": ("OPENROUTER_API_KEY", [("deepseek/deepseek-chat", "0.14", "0.28")]),
    "openai": ("OPENAI_API_KEY", [("gpt-5.6-luna", "0.20", "1.20")]),
    "deepseek": ("DEEPSEEK_API_KEY", [("deepseek-chat", "0.14", "0.28")]),
    "mistral": ("MISTRAL_API_KEY", [("mistral-small-latest", "0.15", "0.60")]),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="handover.bench")
    parser.add_argument("--providers", default="groq,openrouter,deepseek,mistral,openai")
    parser.add_argument("--out", type=Path, default=Path("out/index.html"))
    parser.add_argument("--budget", type=Decimal, default=Decimal("2.00"))
    args = parser.parse_args(argv)

    specs: list[ModelSpec] = []
    callers: dict[str, HttpChatCaller] = {}
    for provider in args.providers.split(","):
        provider = provider.strip()
        if provider not in CATALOG:
            continue
        env_var, models = CATALOG[provider]
        key = os.environ.get(env_var, "").strip()
        if not key:
            print(f"skip {provider}: {env_var} not set")
            continue
        caller = HttpChatCaller(ENDPOINTS[provider], key)
        for model_id, pin, pout in models:
            specs.append(
                ModelSpec(
                    model_id=model_id,
                    price_in_per_mtok=Decimal(pin),
                    price_out_per_mtok=Decimal(pout),
                )
            )
            callers[model_id] = caller

    if not specs:
        print("no providers with keys set — nothing to run")
        return 1

    budget = DailyBudget(args.budget)

    def complete_for(spec: ModelSpec):
        caller = callers[spec.model_id]

        def complete(system: str, user: str, max_tokens: int):
            return caller.complete(
                spec.model_id, system, [{"role": "user", "content": user}], max_tokens
            )

        return complete

    per_cluster = run_index(specs, complete_for, budget)
    cost_shares = (
        {cluster: 1.0 / len(per_cluster) for cluster in per_cluster} if per_cluster else {}
    )
    ranking = compute_index(per_cluster, cost_shares)

    out = render_index(per_cluster, cost_shares, args.out)
    print(f"index: {out.resolve()}  |  spent: ${budget.spent_today():.4f}")
    for i, entry in enumerate(ranking, start=1):
        print(f"  {i}. {entry.model_id}: {entry.score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
