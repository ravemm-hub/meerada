"""Weekly proof for the pilots — numbers first, then the words.

For every business in the experiment registry: the baseline (answers before the lever
started), the latest week, and the change, per engine, from the same ``track`` the public
test-case page uses. Written as ``pilots.json`` (the numbers), ``digest.md`` (one table
for the founder) and one ``<id>.md`` per pilot with the English and Hebrew report mail
the owner receives. Nothing is sent from here.

    meerada visibility pilots --experiments data/experiments.json --state visibility_state.json --out out/pilots
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from handover.visibility.consensus import ENGINE_LABELS
from handover.visibility.experiments import Experiment, load_experiments, track
from handover.visibility.questions import BY_ID
from handover.visibility.state import State

PAGES = "https://meerada.app"
LEVER_WORDS = {
    "guide": "included in the Meerada comparison guide for this question",
    "profile": "a factual profile page published on meerada.app",
    "outreach": "a truthful mention requested on a page the engines already cite",
    "directory": "a listing created from public facts in a directory the engines read",
    "google-business-profile": "Google Business Profile fixes (owner side)",
    "own-site": "answer pages on the business's own site (owner side)",
    "none": "no lever (control)",
}


def _week(exp: Experiment, now: datetime) -> int:
    start = datetime(exp.started.year, exp.started.month, exp.started.day, tzinfo=UTC)
    return max(0, (now - start).days // 7 + 1) if now >= start else 0


def _latest_week(row: dict[str, Any], now: datetime) -> dict[str, dict[str, int]]:
    """Per engine: named / n in the last seven days (the proof round)."""
    since = (now - timedelta(days=7)).isoformat()
    out: dict[str, dict[str, int]] = {}
    for engine, r in row["engines"].items():
        recent = [s for s in r["series"] if s["t"] >= since]
        out[engine] = {
            "n": len(recent),
            "named": sum(1 for s in recent if s["named"]),
            "cited": sum(1 for s in recent if s["cited"]),
        }
    return out


def summarize(
    experiments: list[Experiment], state: State, now: datetime | None = None
) -> list[dict[str, Any]]:
    now = now or datetime.now(tz=UTC)
    engines = sorted({a.engine for a in state.answers if not a.error})
    rows = track(experiments, state, engines)
    by_id = {e.id: e for e in experiments}
    out: list[dict[str, Any]] = []
    for row in rows:
        exp = by_id[row["id"]]
        week = _latest_week(row, now)
        base_named = sum(r["before"]["named"] for r in row["engines"].values())
        base_n = sum(r["before"]["n"] for r in row["engines"].values())
        week_named = sum(w["named"] for w in week.values())
        week_n = sum(w["n"] for w in week.values())
        out.append(
            {
                **{
                    k: row[k]
                    for k in (
                        "id",
                        "business",
                        "domain",
                        "lever",
                        "control",
                        "started",
                        "city",
                        "category",
                        "queries",
                    )
                },
                "week": _week(exp, now),
                "baseline": {
                    "named": base_named,
                    "n": base_n,
                    "per_engine": {e: r["before"] for e, r in row["engines"].items()},
                },
                "latest_week": {"named": week_named, "n": week_n, "per_engine": week},
                "after": {e: r["after"] for e, r in row["engines"].items()},
                "change": (week_named / week_n if week_n else 0.0)
                - (base_named / base_n if base_n else 0.0),
            }
        )
    return out


def _per_engine_line(per: dict[str, dict[str, int]]) -> str:
    return (
        ", ".join(
            f"{ENGINE_LABELS.get(e, e)} {v['named']}/{v['n']}" for e, v in per.items() if v["n"]
        )
        or "no runs yet"
    )


def report_mail(p: dict[str, Any]) -> str:
    q = BY_ID[p["queries"][0]]
    b, w = p["baseline"], p["latest_week"]
    lever = LEVER_WORDS.get(p["lever"], p["lever"])
    case = f"{PAGES}/cases.html"
    verdict_en = (
        "No change yet — expected in the first weeks; the engines re-read pages slowly."
        if w["n"] and w["named"] <= b["named"] * (w["n"] / max(b["n"], 1))
        else (
            "The engines have started naming you."
            if w["named"]
            else "The proof round for this week has not run yet."
        )
    )
    en = f"""Subject: Week {p["week"]} — {p["business"]} in the AI answers for "{q.category} in {q.city}"

Hello,

This week's measurement for {p["business"]} on "{q.text}":

- Before we started: named in {b["named"]} of {b["n"]} answers ({_per_engine_line(b["per_engine"])}).
- This week: named in {w["named"]} of {w["n"]} answers ({_per_engine_line(w["per_engine"])}).
- {verdict_en}

What is in place so far: {lever}. Every run is public, newest first: {case}

Next week we ask the same question again, the same way, and send you the numbers.

Rave Maymon · Meerada · hello@meerada.app
"""
    he = f"""נושא: שבוע {p["week"]} — {p["business"]} בתשובות ה-AI על "{q.category} ב{q.city}"

שלום,

המדידה של השבוע עבור {p["business"]} על השאלה "{q.text}":

- לפני שהתחלנו: נקוב ב-{b["named"]} מתוך {b["n"]} תשובות ({_per_engine_line(b["per_engine"])}).
- השבוע: נקוב ב-{w["named"]} מתוך {w["n"]} תשובות ({_per_engine_line(w["per_engine"])}).

מה כבר במקום: {lever}. כל ריצה פתוחה לציבור, החדשה ראשונה: {case}

בשבוע הבא נשאל שוב את אותה שאלה, באותה דרך, ונשלח את המספרים.

רווה מימון · Meerada · hello@meerada.app
"""
    return f"# {p['business']} — week {p['week']}\n\n- lever: {p['lever']} · since {p['started']} · question: {q.id}\n- baseline {b['named']}/{b['n']} → this week {w['named']}/{w['n']}\n\n## English\n\n```\n{en}```\n\n## עברית\n\n```\n{he}```\n"


def digest(pilots: list[dict[str, Any]], now: datetime) -> str:
    lines = [
        f"# Pilots — {now:%Y-%m-%d}",
        "",
        "| pilot | lever | week | baseline | this week | change |",
        "|---|---|---|---|---|---|",
    ]
    for p in pilots:
        b, w = p["baseline"], p["latest_week"]
        tag = " (control)" if p["control"] else ""
        lines.append(
            f"| {p['business']}{tag} | {p['lever']} | {p['week']} | {b['named']}/{b['n']} | {w['named']}/{w['n']} | {p['change']:+.0%} |"
        )
    moved = [p for p in pilots if not p["control"] and p["latest_week"]["named"] > 0]
    lines += [
        "",
        f"{len(moved)} of {sum(1 for p in pilots if not p['control'])} pilots named at least once this week.",
    ]
    return "\n".join(lines) + "\n"


def build_pilot_reports(
    experiments_path: Path, state: State, out_dir: Path, now: datetime | None = None
) -> list[Path]:
    now = now or datetime.now(tz=UTC)
    out_dir.mkdir(parents=True, exist_ok=True)
    experiments = load_experiments(experiments_path)
    claimed = experiments_path.with_name("pilots.json")
    if claimed != experiments_path:
        experiments += load_experiments(claimed)
    pilots = summarize(experiments, state, now)
    written = [out_dir / "pilots.json", out_dir / "digest.md"]
    (out_dir / "pilots.json").write_text(
        json.dumps(
            {"generated_at": now.isoformat(), "pilots": pilots}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    (out_dir / "digest.md").write_text(digest(pilots, now), encoding="utf-8")
    for p in pilots:
        if p["control"]:
            continue
        path = out_dir / f"{p['id']}.md"
        path.write_text(report_mail(p), encoding="utf-8")
        written.append(path)
    return written
