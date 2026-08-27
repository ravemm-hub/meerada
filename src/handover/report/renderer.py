"""Render the local CPAT report: one self-contained HTML file.

No external CSS, no JS, no network calls (SPEC P7). Output goes to a local path.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from handover.metrics import CoreMetrics, Proportion, WasteBreakdown


def _pct(p: Proportion) -> str:
    if p.value is None:
        return "—"
    ci = ""
    if p.ci_low is not None and p.ci_high is not None:
        ci = f" [{p.ci_low * 100:.1f}-{p.ci_high * 100:.1f}]"
    return f"{p.value * 100:.1f}%{ci} · n={p.n}"


def _usd(value: Decimal | None) -> str:
    return "—" if value is None else f"${value:,.4f}"


def _model_row(name: str, m: CoreMetrics) -> dict[str, Any]:
    return {
        "model": name,
        "n_verified": m.n_verified,
        "success": _pct(m.success_rate),
        "cpat": _usd(m.cpat_usd.value),
        "ttat": "—" if m.ttat_seconds.value is None else f"{m.ttat_seconds.value:,.1f}s",
        "attempts": (
            "—" if m.attempts_per_win.value is None else f"{m.attempts_per_win.value:.2f}"
        ),
    }


def render_report(
    *,
    overall: CoreMetrics,
    per_model: dict[str, CoreMetrics],
    waste: WasteBreakdown,
    out_path: Path,
    generated_at: datetime | None = None,
) -> Path:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    waste_rows = [
        ("Retries (failed attempts of eventually-successful tasks)", waste.retry),
        ("Excess reasoning (above cluster p50 of successes)", waste.reasoning),
        ("Uncached repeated context", waste.context),
        ("Dead tasks (never succeeded)", waste.dead),
    ]
    html = env.get_template("report.html.j2").render(
        generated_at=(generated_at or datetime.now(tz=UTC)).strftime("%Y-%m-%d %H:%MZ"),
        overall=_model_row("all models", overall),
        unknown_rate=_pct(overall.unknown_rate),
        unknown_high=(overall.unknown_rate.value or 0.0) > 0.30,
        n_tasks=overall.n_tasks,
        n_unknown=overall.n_unknown,
        model_rows=[_model_row(name, metrics) for name, metrics in per_model.items()],
        waste_rows=[
            {
                "name": name,
                "amount": _usd(component.amount_usd),
                "grade": component.evidence_grade,
                "n": component.n_traces,
            }
            for name, component in waste_rows
        ],
        waste_total=_usd(waste.total_usd),
        n_unpriced=waste.n_unpriced_traces,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
