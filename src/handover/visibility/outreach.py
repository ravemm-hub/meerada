"""Outreach drafts for the pilots — one file per business, English and Hebrew, for the
founder to read and send. Nothing is sent from here.

The mail is a single, first approach to a business asking whether it wants the free pilot
(Israel's anti-spam rule allows one approach to a business asking for consent; CAN-SPAM and
PECR allow B2B with opt-out). It states the measured numbers, links to the public page,
offers one month with no card, and says how to say no.

    meerada visibility outreach --experiments data/experiments.json --state visibility_state.json --out out/outreach
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from handover.visibility.compare import same_business
from handover.visibility.questions import BY_ID
from handover.visibility.state import State

PAGES = "https://meerada.app"


def named_counts(state: State, query_id: str, names: list[str]) -> dict[str, tuple[int, int]]:
    """Per engine: (runs naming any of ``names``, runs) for one question."""
    per: dict[str, list[int]] = {}
    for a in state.answers:
        if a.query_id != query_id or a.error:
            continue
        hit = any(same_business(n, x) for n in names for x in a.names)
        per.setdefault(a.engine, [0, 0])
        per[a.engine][0] += int(hit)
        per[a.engine][1] += 1
    return {e: (v[0], v[1]) for e, v in sorted(per.items())}


def _lead_page(leads: list[dict[str, Any]], business: str, query_id: str) -> str | None:
    for r in leads:
        if r["query_id"] == query_id and same_business(r["business"], business):
            return f"{PAGES}/gap/{r['slug']}.html"
    return None


def draft(exp: dict[str, Any], counts: dict[str, tuple[int, int]], page: str | None) -> str:
    q = BY_ID[exp["queries"][0]]
    name = exp["business"]
    total_named = sum(n for n, _ in counts.values())
    total_runs = sum(r for _, r in counts.values())
    per = ", ".join(f"{e} {n}/{r}" for e, (n, r) in counts.items())
    link = page or f"{PAGES}/s/{q.id}.html"
    domain = exp.get("domain") or "(no website — contact via the Maps listing / social page)"
    en = f"""Subject: {name} is not in the AI answers for "{q.category} in {q.city}" — a free month to change that

Hello,

I run Meerada, a small service that measures what ChatGPT and the other AI assistants answer when people ask them for a {q.category} in {q.city}.

We asked the engines "{q.text}" {total_runs} times. {name} was named {total_named} times ({per}). The measurement, and who the engines name instead, is public here: {link}

That gap is fixable, and we would like to fix it for you free for one month — no card, no commitment — as one of our first ten pilots:
- a factual page about {name} in English and in the local language on meerada.app, the kind of page the engines read;
- a check of the pages the engines cite for this question, and what is missing from each;
- a short fix list for your own site and Google listing, ready to paste;
- the same question asked again every week, with the change shown run by run.

If after the month you see no change, you owe nothing and we say so publicly. If you see a change, the service is 49 $ a month and you can stop any time.

This is a one-time message to ask whether you are interested. If you are not, reply "no" and we will not write again.

Rave Maymon
Meerada · hello@meerada.app
"""
    he = f"""נושא: {name} לא מופיע בתשובות ה-AI על "{q.category} ב{q.city}" — חודש חינם לשנות את זה

שלום,

אני מפעיל את Meerada, שירות קטן שמודד מה ChatGPT ושאר עוזרי ה-AI עונים כששואלים אותם על {q.category} ב{q.city}.

שאלנו את המנועים "{q.text}" {total_runs} פעמים. {name} נקוב {total_named} פעמים ({per}). המדידה, ומי כן נקוב, פתוחה כאן: {link}

את הפער הזה אפשר לסגור, ואנחנו רוצים לעשות את זה בשבילכם חינם לחודש — בלי כרטיס אשראי ובלי התחייבות — כאחד מעשרת הפיילוטים הראשונים שלנו:
- עמוד עובדתי על {name} באנגלית ובעברית ב-meerada.app, מהסוג שהמנועים קוראים;
- בדיקה של העמודים שהמנועים מצטטים לשאלה הזו, ומה חסר בכל אחד;
- רשימת תיקונים קצרה לאתר ולרישום בגוגל, מוכנה להדבקה;
- אותה שאלה נשאלת שוב כל שבוע, והשינוי מוצג ריצה אחר ריצה.

אם אחרי החודש אין שינוי — לא חייבים כלום, ואנחנו אומרים את זה בפומבי. אם יש שינוי, השירות עולה 149 ₪ לחודש ואפשר להפסיק בכל רגע.

זו פנייה חד-פעמית כדי לשאול אם זה מעניין אתכם. אם לא, השיבו "לא" ולא נכתוב שוב.

רווה מימון
Meerada · hello@meerada.app
"""
    head = f"# {name}\n\n- pilot id: {exp['id']} · lever: {exp.get('lever')} · question: {q.id}\n- website: {domain}\n- baseline: {per} (total {total_named}/{total_runs})\n- public page: {link}\n- to: (find the contact address on the website; the founder sends — nothing is sent from here)\n\n"
    return head + "## English\n\n```\n" + en + "```\n\n## עברית\n\n```\n" + he + "```\n"


def build_outreach(
    experiments_path: Path, state: State, out_dir: Path, leads_path: Path | None = None
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    exps = json.loads(experiments_path.read_text(encoding="utf-8"))["experiments"]
    leads: list[dict[str, Any]] = []
    if leads_path is not None and leads_path.exists():
        leads = json.loads(leads_path.read_text(encoding="utf-8"))["leads"]
    written: list[Path] = []
    for exp in exps:
        if exp.get("control"):
            continue
        names = [exp["business"], *exp.get("aliases", [])]
        counts = named_counts(state, exp["queries"][0], names)
        page = _lead_page(leads, exp["business"], exp["queries"][0])
        path = out_dir / f"{exp['id']}.md"
        path.write_text(draft(exp, counts, page), encoding="utf-8")
        written.append(path)
    return written
