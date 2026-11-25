"""The consensus ranking: for one question, which options do the AI engines name, how
consistently, and how high. This is the public "what the AI shows" order.

score(option) = Σ_engines w_e · (runs naming it / runs) · mean(1/√position)

Weights follow consumer reach (ChatGPT first). Every score carries the number of runs
behind it. Nothing here can be bought; the weights live in code, not in a config.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from math import sqrt
from typing import Any

from handover.visibility.extract import source_family
from handover.visibility.state import Answer

ENGINE_WEIGHTS: dict[str, float] = {
    "chatgpt": 0.40,
    "chatgpt5": 0.25,
    "claude": 0.15,
    "perplexity": 0.10,
    "gemini": 0.08,
    "grok": 0.06,
    "mistral": 0.03,
}
ENGINE_LABELS: dict[str, str] = {
    "chatgpt": "ChatGPT",
    "chatgpt5": "ChatGPT (fan-out)",
    "claude": "Claude",
    "perplexity": "Perplexity",
    "gemini": "Gemini",
    "grok": "Grok",
    "mistral": "Mistral",
}


def rank(answers: list[Answer], limit: int = 15) -> dict[str, Any]:
    """Rank the options named across all successful answers to one question."""
    ok = [a for a in answers if not a.error]
    runs_by_engine: Counter[str] = Counter(a.engine for a in ok)
    named: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )  # key→engine→positions
    display: dict[str, str] = {}
    sources: dict[str, Counter[str]] = defaultdict(Counter)
    for a in ok:
        for pos, (key, name) in enumerate(zip(a.name_keys, a.names, strict=False), start=1):
            named[key][a.engine].append(pos)
            display.setdefault(key, name)
            for c in a.citations:
                sources[key][source_family(c)] += 1
    results: list[dict[str, Any]] = []
    for key, by_engine in named.items():
        score = 0.0
        engines: dict[str, Any] = {}
        for engine, runs in runs_by_engine.items():
            positions = by_engine.get(engine, [])
            share = len(positions) / runs if runs else 0.0
            pos_factor = (
                (sum(1 / sqrt(p) for p in positions) / len(positions)) if positions else 0.0
            )
            score += ENGINE_WEIGHTS.get(engine, 0.05) * share * pos_factor
            engines[engine] = {
                "named": len(positions),
                "runs": runs,
                "best_position": min(positions) if positions else None,
            }
        all_pos = [p for ps in by_engine.values() for p in ps]
        results.append(
            {
                "name": display[key],
                "key": key,
                "score": round(score, 4),
                "named_runs": len(all_pos),
                "runs": sum(runs_by_engine.values()),
                "best_position": min(all_pos) if all_pos else None,
                "engines": engines,
                "sources": [f for f, _ in sources[key].most_common(3)],
            }
        )
    results.sort(key=lambda r: (-r["score"], -r["named_runs"], r["name"].lower()))
    last = max((a.asked_at for a in ok), default=None)
    return {
        "runs": sum(runs_by_engine.values()),
        "engines": {e: n for e, n in runs_by_engine.items()},
        "engine_labels": {e: ENGINE_LABELS.get(e, e) for e in runs_by_engine},
        "weights": {e: ENGINE_WEIGHTS.get(e, 0.05) for e in runs_by_engine},
        "last_asked": last.isoformat() if isinstance(last, datetime) else None,
        "results": results[:limit],
        "distinct": len(results),
    }
