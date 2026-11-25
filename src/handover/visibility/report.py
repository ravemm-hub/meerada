"""Aggregate the stored answers into the numbers the page shows. Every rate is a
``Proportion`` (value, n, Wilson 95% CI); means carry their n. Plain dicts out,
so the result is the page's JSON as-is.

Blocks: per engine (coverage, candidates, sources, how it chooses), per intent x
engine (the same, sliced by kind of search), stability (does the same question get
the same names a few days later), overlap between engines, most-named options,
experiments, and every question x engine.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from typing import Any

from handover.metrics.core import Proportion, proportion
from handover.visibility.experiments import Experiment, track
from handover.visibility.extract import source_family
from handover.visibility.features import jaccard
from handover.visibility.questions import BY_ID, INTENT_LABELS, Query
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


def _f(a: Answer, key: str) -> float:
    return float(a.features.get(key, 0.0))


def _choosing(ok: list[Answer]) -> dict[str, Any]:
    """How an engine chooses, from the answers' own features."""
    named = [a for a in ok if a.name_keys]
    candidates = sum(_f(a, "candidates") for a in named)
    cites = sum(_f(a, "cites") for a in ok)
    return {
        "candidates": _mean([_f(a, "candidates") for a in named]),
        "pick_rate": _prop(proportion(sum(int(_f(a, "has_pick")) for a in named), len(named))),
        "table_rate": _prop(proportion(sum(int(_f(a, "has_table")) for a in named), len(named))),
        "rated_share": (sum(_f(a, "rated") for a in named) / candidates) if candidates else None,
        "priced_share": (sum(_f(a, "priced") for a in named) / candidates) if candidates else None,
        "own_site_share": (sum(_f(a, "own_site") for a in named) / candidates)
        if candidates
        else None,
        "listicle_share": (sum(_f(a, "listicle_cites") for a in ok) / cites) if cites else None,
        "hosts_per_answer": _mean([_f(a, "distinct_hosts") for a in ok]),
    }


def _stability(state: State, engine: str, query_ids: set[str] | None = None) -> dict[str, Any]:
    """Jaccard between the two latest successful answers to the same question."""
    by_q: dict[str, list[Answer]] = defaultdict(list)
    for a in state.answers:
        if a.engine == engine and not a.error and (query_ids is None or a.query_id in query_ids):
            by_q[a.query_id].append(a)
    scores: list[float] = []
    for answers in by_q.values():
        if len(answers) < 2:
            continue
        answers.sort(key=lambda a: a.asked_at)
        j = jaccard(answers[-1].name_keys, answers[-2].name_keys)
        if j is not None:
            scores.append(j)
    return _mean(scores)


def _sources(ok: list[Answer], limit: int = 8) -> list[dict[str, Any]]:
    families = Counter(source_family(c) for a in ok for c in a.citations)
    total = sum(families.values())
    return [
        {"family": fam, "count": cnt, "share": cnt / total if total else None}
        for fam, cnt in families.most_common(limit)
    ]


def _engine_block(engine: str, answers: list[Answer], state: State) -> dict[str, Any]:
    ok = [a for a in answers if not a.error]
    named = [a for a in ok if a.name_keys]
    mentions = Counter(k for a in ok for k in a.name_keys)
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
        "sources": _sources(ok),
        "choosing": _choosing(ok),
        "stability": _stability(state, engine),
        "latency_ms": _mean([float(a.latency_ms) for a in ok]),
        "cost_usd": str(sum(float(a.cost_usd) for a in answers)),
    }


def _intent_blocks(
    latest: dict[tuple[str, str], Answer],
    queries: tuple[Query, ...],
    engines: list[str],
    state: State,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for intent, label in INTENT_LABELS.items():
        qids = {q.id for q in queries if q.intent == intent}
        if not qids:
            continue
        per_engine: dict[str, Any] = {}
        for e in engines:
            answers = [a for (eng, qid), a in latest.items() if eng == e and qid in qids]
            ok = [a for a in answers if not a.error]
            named = [a for a in ok if a.name_keys]
            per_engine[e] = {
                "asked": len(answers),
                "named_rate": _prop(proportion(len(named), len(ok))),
                "searched_rate": _prop(proportion(sum(1 for a in ok if a.searches), len(ok))),
                "sources": _sources(ok, limit=3),
                "choosing": _choosing(ok),
                "stability": _stability(state, e, qids),
            }
        rows.append({"intent": intent, "label": label, "queries": len(qids), "engines": per_engine})
    return rows


def _overlap(latest: dict[tuple[str, str], Answer], engines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for a, b in combinations(engines, 2):
        scores: list[float] = []
        for qid in BY_ID:
            x, y = latest.get((a, qid)), latest.get((b, qid))
            if not x or not y or x.error or y.error:
                continue
            j = jaccard(x.name_keys, y.name_keys)
            if j is not None:
                scores.append(j)
        rows.append({"a": a, "b": b, "jaccard": _mean(scores)})
    return rows


def _top_names(latest: dict[tuple[str, str], Answer], limit: int = 25) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for (engine, qid), a in latest.items():
        if a.error:
            continue
        q = BY_ID.get(qid)
        for key, name in zip(a.name_keys, a.names, strict=False):
            row = by_key.setdefault(
                key,
                {
                    "name": name,
                    "mentions": 0,
                    "engines": set(),
                    "cities": set(),
                    "cats": set(),
                    "intents": set(),
                },
            )
            row["mentions"] += 1
            row["engines"].add(engine)
            if q:
                row["cities"].add(q.city)
                row["cats"].add(q.category)
                row["intents"].add(q.intent)
    rows = sorted(by_key.values(), key=lambda r: (-r["mentions"], r["name"]))[:limit]
    return [
        {
            "name": r["name"],
            "mentions": r["mentions"],
            "engines": sorted(r["engines"]),
            "cities": sorted(r["cities"]),
            "categories": sorted(r["cats"]),
            "intents": sorted(r["intents"]),
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
                    "searched": bool(a.searches),
                    "asked_at": a.asked_at.isoformat(),
                }
        rows.append(
            {
                "id": q.id,
                "city": q.city,
                "country": q.country,
                "lang": q.lang,
                "category": q.category,
                "intent": q.intent,
                "text": q.text,
                "engines": cells,
            }
        )
    return rows


def build_report(
    state: State,
    queries: tuple[Query, ...],
    engines: list[str],
    now: datetime,
    experiments: list[Experiment] | None = None,
) -> dict[str, Any]:
    latest = state.latest()
    per_engine = {e: [a for (eng, _), a in latest.items() if eng == e] for e in engines}
    return {
        "generated_at": now.isoformat(),
        "method": {
            "queries": len(queries),
            "intents": [
                {"intent": i, "label": INTENT_LABELS[i], "n": sum(q.intent == i for q in queries)}
                for i in INTENT_LABELS
            ],
            "cities": sorted({q.city for q in queries}),
            "categories": sorted({q.category for q in queries}),
            "nudge": "Please name specific ones / models / products / companies.",
            "extraction": "program (lists, bold names, links, Maps citations) — evidence derived",
            "features": "read from the answer text and citations — evidence derived",
            "interval": "Wilson 95%",
        },
        "engines": [_engine_block(e, per_engine[e], state) for e in engines],
        "intents": _intent_blocks(latest, queries, engines, state),
        "skipped": state.skipped,
        "overlap": _overlap(latest, engines),
        "top_names": _top_names(latest),
        "experiments": track(experiments or [], state, engines),
        "queries": _query_rows(latest, queries, engines),
        "answers_total": len(state.answers),
    }
