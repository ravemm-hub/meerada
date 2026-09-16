"""Deploy-time extras from the live data: per-model badges, an RSS feed of what
changed, and the Meerada Index (a composite of the top measured models).

    python scripts/build_feeds.py --state grade_state.json --live models_live.json --out site_dir

Pure files in, pure files out; no network. Runs inside deploy_pages.sh on the
gh-pages copies, so the badges always reflect the published ranking.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


def safe_id(model_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model_id)


def badge_svg(model_id: str, rank: int, score: float, cpat: float | None) -> str:
    right = f"#{rank} · {score:.1f}" + (f" · ${cpat:.4f}/task" if cpat is not None else "")
    lw, rw = 118, 12 + int(len(right) * 6.6)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{lw + rw}" height="20" role="img" '
        f'aria-label="Meerada: {escape(right)}">'
        f"<title>{escape(model_id)} on Meerada — {escape(right)}</title>"
        f'<rect width="{lw}" height="20" rx="3" fill="#0F172A"/>'
        f'<rect x="{lw}" width="{rw}" height="20" rx="3" fill="#0E8A7E"/>'
        f'<rect x="{lw - 3}" width="6" height="20" fill="#0E8A7E"/>'
        '<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="8" y="14">ranked on meerada.app</text>'
        f'<text x="{lw + 6}" y="14">{escape(right)}</text></g></svg>'
    )


def measured(cards: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [c for c in cards.values() if c and c.get("score") is not None and c.get("n", 0) >= 30]
    rows.sort(key=lambda c: -float(c["score"]))
    return rows


def index_value(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The Meerada Index: mean grade of the top ten measured models, and the
    median cost of a done task among them — one number for 'how good and how
    cheap is the frontier right now'."""
    top = rows[:10]
    if not top:
        return {"value": None, "n": 0}
    grades = [float(c["score"]) for c in top]
    cpats = sorted(
        float(c["econ"]["cpat_usd"])
        for c in top
        if c.get("econ") and c["econ"].get("cpat_usd") is not None
    )
    med = cpats[len(cpats) // 2] if cpats else None
    return {
        "value": round(sum(grades) / len(grades), 2),
        "median_cpat_usd": med,
        "n": len(top),
        "members": [c["model_id"] for c in top],
        "as_of": datetime.now(tz=UTC).isoformat(timespec="minutes"),
    }


def feed_xml(rows: list[dict[str, Any]], live: dict[str, Any]) -> str:
    now = datetime.now(tz=UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items: list[str] = []
    for c in rows[:15]:
        hist = c.get("history") or []
        delta = (hist[-1] - hist[-2]) if len(hist) >= 2 else 0.0
        econ = c.get("econ") or {}
        cpat = econ.get("cpat_usd")
        title = f"{c['model_id']}: grade {float(c['score']):.1f} ({delta:+.1f})"
        desc = f"n={c.get('n')} · status {c.get('status')}" + (
            f" · cost per done task ${cpat:.4f}" if cpat is not None else ""
        )
        items.append(
            "<item><title>{t}</title><link>https://meerada.app/#measured-wrap</link>"
            '<guid isPermaLink="false">{g}</guid><description>{d}</description></item>'.format(
                t=escape(title),
                g=escape(f"{c['model_id']}@{c.get('updated_at', '')}"),
                d=escape(desc),
            )
        )
    new = sorted(
        (m for m in (live.get("models") or []) if (m.get("age_days") or 999) <= 7),
        key=lambda m: m.get("age_days") or 0,
    )[:15]
    for m in new:
        items.append(
            "<item><title>{t}</title><link>https://meerada.app/#new-wrap</link>"
            '<guid isPermaLink="false">{g}</guid><description>{d}</description></item>'.format(
                t=escape(f"New model: {m['id']}"),
                g=escape(f"new:{m['id']}"),
                d=escape(
                    f"{m.get('vendor', '')} · ${m.get('price_in')}/{m.get('price_out')} "
                    f"per M tokens · context {m.get('context')}"
                ),
            )
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        "<title>Meerada — the live AI model exchange</title><link>https://meerada.app</link>"
        "<description>Grade moves and new models, measured hourly on verifiable tasks."
        "</description>"
        f"<lastBuildDate>{now}</lastBuildDate>{''.join(items)}</channel></rss>"
    )


def build(state: Path, live: Path, out: Path) -> dict[str, int]:
    cards = (json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}).get(
        "cards"
    ) or {}
    feed = json.loads(live.read_text(encoding="utf-8")) if live.exists() else {}
    rows = measured(cards)
    (out / "badges").mkdir(parents=True, exist_ok=True)
    for rank, c in enumerate(rows, 1):
        econ = c.get("econ") or {}
        (out / "badges" / f"{safe_id(c['model_id'])}.svg").write_text(
            badge_svg(c["model_id"], rank, float(c["score"]), econ.get("cpat_usd")),
            encoding="utf-8",
        )
    (out / "index.json").write_text(json.dumps(index_value(rows), indent=1), encoding="utf-8")
    (out / "feed.xml").write_text(feed_xml(rows, feed), encoding="utf-8")
    return {"badges": len(rows), "index_members": min(10, len(rows))}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--live", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    print("feeds:", build(a.state, a.live, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
