"""Aggregate the newest answers into the numbers the page shows. Every rate is a
``Proportion`` (value, n, Wilson 95% CI); means carry their n. Plain dicts out,
so the result is the page's JSON as-is.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from itertools import combinations
from typing import Any

from handover.metrics.core import Proportion, proportion
from handover.visibility.extract import source_family
from handover.visibility.questions import BY_ID, Query
from handover.visibility.state import Answer, State

ENGINE_LABELS = {
    "chatgpt": "ChatGPT (web search)",
    "perplexity": "Perplexity (Sonar)",
    "gemini": "Gemini (Google grounding)",
    "claude": "Claude (web search)",
}


def _prop(p: Proportion) -> dict[str, Any]:
    return {"value": p.value, "n": p.n, "ci_low": p.ci_low, "ci_high": p.ci_high}


def _mean(values: list[float]) -> dict[str, Any]:
    return {"value": sum(values) / len(values) if values else None, "n": len(values)}


def _engine_block(engine: str, answers: list[Answer]) -> dict[str, Any]:
    ok = [a for a in answers if not a.error]
    named = [a for a in ok if a.name_keys]
    mentions = Counter(k for a in ok for k in a.name_keys)
    families = Counter(source_family(c) for a in ok for c in a.citations)
    total_cites = sum(families.values())
    return {
        "engine": engine,
        "label": ENGINE_LABELS.get(engine, engine),
        "model": answers[-1].model if answers else "",
        "asked": len(answers),
        "errors": len(answers) - len(ok),
        "last_error": next((a.error for a in reversed(answers) if a.error), None),
        "named_rate": _prop(proportion(len(named), len(ok))),
        "searched_rate": _prop(proportion(sum(1 for a in ok if a.searches), len(ok))),
        "names_per_answer": _mean([float(len(a.name_keys)) for a in named]),
        "distinct_names": len(mentions),
        "total_mentions": sum(mentions.values()),
        "cited_per_answer": _mean([float(len(a.citations)) for a in ok]),
        "sources": [
            {"family": fam, "count": cnt, "share": cnt / total_cites if total_cites else None}
            for fam, cnt in families.most_common(8)
        ],
        "latency_ms": _mean([float(a.latency_ms) for a in ok]),
        "cost_usd": str(sum(float(a.cost_usd) for a in answers)),
    }


def _overlap(latest: dict[tuple[str, str], Answer], engines: list[str]) -> list[dict[str, Any]]:
    """Mean Jaccard of the name sets two engines give the same question."""
    rows: list[dict[str, Any]] = []
    for a, b in combinations(engines, 2):
        scores: list[float] = []
        for qid in BY_ID:
            x, y = latest.get((a, qid)), latest.get((b, qid))
            if not x or not y or x.error or y.error or not (x.name_keys or y.name_keys):
                continue
            sx, sy = set(x.name_keys), set(y.name_keys)
            scores.append(len(sx & sy) / len(sx | sy))
        rows.append({"a": a, "b": b, "jaccard": _mean(scores)})
    return rows


def _top_names(latest: dict[tuple[str, str], Answer], limit: int = 20) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for (engine, qid), a in latest.items():
        if a.error:
            continue
        q = BY_ID.get(qid)
        for key, name in zip(a.name_keys, a.names, strict=False):
            row = by_key.setdefault(
                key, {"name": name, "mentions": 0, "engines": set(), "cities": set(), "cats": set()}
            )
            row["mentions"] += 1
            row["engines"].add(engine)
            if q:
                row["cities"].add(q.city)
                row["cats"].add(q.category)
    rows = sorted(by_key.values(), key=lambda r: (-r["mentions"], r["name"]))[:limit]
    return [
        {
            "name": r["name"],
            "mentions": r["mentions"],
            "engines": sorted(r["engines"]),
            "cities": sorted(r["cities"]),
            "categories": sorted(r["cats"]),
        }
        for r in rows
    ]


def _query_rows(
    latest: dict[tuple[str, str], Answer], queries: tuple[Query, ...], engines: list[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for q in queries:
        cells: dict[str, Any] = {}
        for e in engines:
            a = latest.get((e, q.id))
            if a is None:
                cells[e] = None
            elif a.error:
                cells[e] = {"error": a.error[:120], "asked_at": a.asked_at.isoformat()}
            else:
                cells[e] = {
                    "names": a.names,
                    "sources": sorted({source_family(c) for c in a.citations}),
                    "asked_at": a.asked_at.isoformat(),
                }
        rows.append(
            {
                "id": q.id,
                "city": q.city,
                "country": q.country,
                "lang": q.lang,
                "category": q.category,
                "text": q.text,
                "engines": cells,
            }
        )
    return rows


def build_report(
    state: State, queries: tuple[Query, ...], engines: list[str], now: datetime
) -> dict[str, Any]:
    latest = state.latest()
    per_engine = {e: [a for (eng, _), a in latest.items() if eng == e] for e in engines}
    cities = sorted({q.city for q in queries})
    return {
        "generated_at": now.isoformat(),
        "method": {
            "queries": len(queries),
            "cities": cities,
            "categories": sorted({q.category for q in queries}),
            "nudge": "Who do you recommend? Please name specific ones.",
            "extraction": "program (list items, bold names, links) — evidence derived",
            "interval": "Wilson 95%",
        },
        "engines": [_engine_block(e, per_engine[e]) for e in engines],
        "skipped": state.skipped,
        "overlap": _overlap(latest, engines),
        "top_names": _top_names(latest),
        "queries": _query_rows(latest, queries, engines),
        "answers_total": len(state.answers),
    }
