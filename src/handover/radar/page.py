"""Render the deprecation radar as a self-contained page (the public lead magnet).

No network, no content — model ids and dates only. The page invites the reader
to run `meerada pack` and get a measured gap report for their own workload.
"""

from collections.abc import Sequence
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from handover.branding import BRAND_NAME
from handover.radar.deprecations import RadarEntry

_TEMPLATE_DIR = Path(__file__).parent.parent / "report" / "templates"


def _row(entry: RadarEntry) -> dict[str, object]:
    if entry.days_left < 0:
        countdown = "retired"
    elif entry.days_left == 0:
        countdown = "today"
    else:
        countdown = f"{entry.days_left} days"
    reps = [
        {
            "model_id": r.model_id,
            "grade": "—" if r.grade is None else f"{r.grade:.0f}",
            "delta": (
                ""
                if r.grade_delta is None
                else (f"+{r.grade_delta:.0f}" if r.grade_delta >= 0 else f"{r.grade_delta:.0f}")
            ),
            "delta_class": (
                "" if r.grade_delta is None else ("up" if r.grade_delta >= 0 else "down")
            ),
        }
        for r in entry.replacements
    ]
    return {
        "provider": entry.provider,
        "model_id": entry.model_id,
        "retires_on": entry.retires_on.isoformat(),
        "countdown": countdown,
        "urgency": entry.urgency,
        "notes": entry.notes,
        "replacements": reps,
    }


def render_radar(entries: Sequence[RadarEntry], out_path: Path, *, today: date) -> Path:
    env = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
    )
    n_actionable = sum(1 for e in entries if e.urgency in ("critical", "soon"))
    html = env.get_template("radar.html.j2").render(
        brand=BRAND_NAME,
        today=today.isoformat(),
        n_total=len(entries),
        n_actionable=n_actionable,
        rows=[_row(e) for e in entries],
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
