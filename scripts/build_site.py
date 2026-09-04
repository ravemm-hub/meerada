"""Assemble the full public Meerada site into ./site for static hosting.

Generates the live pages from the engine (grade board, deprecation radar) and
copies the hand-authored pages (landing, market), producing a self-contained
folder any static host serves: GitHub Pages, Cloudflare Pages, Netlify, S3.
Run: python scripts/build_site.py
"""

import base64
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from handover.bench import initial_state, render_board, tick
from handover.bench.discovery import CatalogModel
from handover.metrics.core import proportion
from handover.radar import build_radar, load_deprecations, render_radar
from handover.replay.budget import DailyBudget

ROOT = Path(__file__).parent.parent
SITE = ROOT / "site"
OUT = ROOT / "out"


def build_grade_board() -> None:
    """A demo board from illustrative data — ONLY as a placeholder when no real
    board exists yet. The live board (grade.html + grade_state.json) is written
    to gh-pages by the hourly live-grade workflow and must never be overwritten."""
    if (SITE / "grade.html").exists():
        return
    now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    demo = {
        "claude-sonnet-5": (88.0, proportion(602, 640)),
        "gpt-5.6-terra": (84.0, proportion(560, 640)),
        "deepseek-v4-flash": (79.0, proportion(520, 640)),
        "grok-4.6": (82.0, proportion(27, 30)),
    }
    state = initial_state()
    state, _ = tick(
        state,
        lambda: [CatalogModel(provider="x", model_id=m) for m in demo],
        lambda m: demo[m],
        DailyBudget(Decimal("100")),
        now,
    )
    render_board(list(state.cards.values()), SITE / "grade.html", generated_at=now)


def build_radar_page() -> None:
    deps = load_deprecations(ROOT / "data" / "deprecations_seed.json")
    today = date(2026, 8, 29)
    render_radar(build_radar(deps, today), SITE / "radar.html", today=today)


def embed_download() -> None:
    """Base64-embed the wheel so the static site can hand it over with no server."""
    wheel = next((ROOT / "dist").glob("*.whl"), None)
    if wheel:
        b64 = base64.b64encode(wheel.read_bytes()).decode()
        (SITE / "meerada-wheel.txt").write_text(b64, encoding="utf-8")


def main() -> None:
    SITE.mkdir(exist_ok=True)
    # All hand-authored pages (index, market, llmanager, dashboard) live in site/
    # and are the source of truth — nothing here copies over them.
    build_grade_board()
    build_radar_page()
    embed_download()
    (SITE / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages: serve as-is
    print(f"site assembled at {SITE}")
    for f in sorted(SITE.glob("*")):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()
