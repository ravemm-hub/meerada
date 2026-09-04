"""The public Meerada Grade board — the living ranking, with confidence shown.

Renders GradeCards as a ranked board where every row carries its status
(provisional / confirmed / stale), sample size and CI width. This is the whole
point of the measurement: a grade is never a bare number, so the reader can
trust it or discount it on sight.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from handover.bench.lifecycle import GradeCard
from handover.branding import BRAND_NAME

_TEMPLATE_DIR = Path(__file__).parent.parent / "report" / "templates"


def _row(rank: int, card: GradeCard) -> dict[str, object]:
    q = card.quality.value
    ci = (
        "—"
        if card.quality.ci_low is None or card.quality.ci_high is None
        else f"{card.quality.ci_low * 100:.0f}-{card.quality.ci_high * 100:.0f}"
    )
    return {
        "rank": rank,
        "model_id": card.model_id,
        "score": "—" if card.score is None else f"{card.score:.0f}",
        "score_pct": 0 if card.score is None else max(0, min(100, round(card.score))),
        "score_class": (
            "low"
            if card.score is None or card.score < 60
            else ("mid" if card.score < 80 else "good")
        ),
        "quality": "—" if q is None else f"{q * 100:.1f}%",
        "ci": ci,
        "n": f"{card.n:,}",
        "status": card.status,
        "updated": card.updated_at.strftime("%Y-%m-%d %H:%MZ"),
        "cpat": (
            "—" if card.econ is None or card.econ.cpat_usd is None
            else f"${card.econ.cpat_usd:.5f}"
        ),
        "price_note": "" if card.econ is None else card.econ.price_note,
        "ttat": (
            "—" if card.econ is None or card.econ.ttat_s is None else f"{card.econ.ttat_s:.1f}s"
        ),
    }


def render_board(cards: Sequence[GradeCard], out_path: Path, *, generated_at: datetime) -> Path:
    publishable = sorted(
        (c for c in cards if c.is_publishable), key=lambda c: c.score or -1.0, reverse=True
    )
    provisional = [c for c in cards if c.status == "provisional"]
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("grade_board.html.j2").render(
        brand=BRAND_NAME,
        generated_at=generated_at.strftime("%Y-%m-%d %H:%MZ"),
        rows=[_row(i + 1, c) for i, c in enumerate(publishable)],
        n_confirmed=sum(1 for c in publishable if c.status == "confirmed"),
        n_provisional=len(provisional),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
