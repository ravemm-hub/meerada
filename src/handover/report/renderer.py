"""Render the local report: a ranked, CoinMarketCap-style model leaderboard.

One self-contained HTML file — inline CSS/JS only, no network calls (SPEC P7).
Each model row expands on click into the full numeric analysis.

The HV score here is the §4.3 three-axis formula (quality 0.6, speed 0.2,
value 0.2) min-max normalized across the models in this report. Until P1
clusters exist this normalization spans the whole workload — a labelled P0
approximation of the per-cluster rule.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict

from handover.branding import BRAND_NAME, GRADE_NAME
from handover.metrics import (
    CoreMetrics,
    ModelPrice,
    Proportion,
    TaskTraces,
    WasteBreakdown,
    compute_core,
    compute_waste,
)

WEIGHTS = (0.6, 0.2, 0.2)  # quality, speed, value (SPEC §4.3 defaults)


class ModelReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    metrics: CoreMetrics
    waste: WasteBreakdown
    total_cost_usd: Decimal
    tokens_input: int
    tokens_output: int
    tokens_reasoning: int


def build_model_reports(
    items: Sequence[TaskTraces], prices: Mapping[str, ModelPrice]
) -> list[ModelReport]:
    groups: dict[str, list[TaskTraces]] = {}
    for item in items:
        groups.setdefault(item.task.models_used[-1], []).append(item)
    reports = []
    for name, group in sorted(groups.items()):
        tasks = [item.task for item in group]
        reports.append(
            ModelReport(
                name=name,
                metrics=compute_core(tasks),
                waste=compute_waste(group, prices),
                total_cost_usd=sum((t.total_cost_usd for t in tasks), Decimal("0")),
                tokens_input=sum(t.total_tokens.input for t in tasks),
                tokens_output=sum(t.total_tokens.output for t in tasks),
                tokens_reasoning=sum(t.total_tokens.reasoning for t in tasks),
            )
        )
    return reports


def _pct(p: Proportion) -> str:
    if p.value is None:
        return "—"
    ci = ""
    if p.ci_low is not None and p.ci_high is not None:
        ci = f" [{p.ci_low * 100:.1f}-{p.ci_high * 100:.1f}]"
    return f"{p.value * 100:.1f}%{ci}"


def _usd(value: Decimal | None) -> str:
    return "—" if value is None else f"${value:,.4f}"


def _minmax(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _scores(models: Sequence[ModelReport]) -> dict[str, float | None]:
    eligible = [
        m
        for m in models
        if m.metrics.success_rate.value is not None
        and m.metrics.cpat_usd.value
        and m.metrics.ttat_seconds.value
    ]
    if not eligible:
        return {m.name: None for m in models}
    quality = _minmax([m.metrics.success_rate.value or 0.0 for m in eligible])
    speed = _minmax([math.log(1.0 / (m.metrics.ttat_seconds.value or 1.0)) for m in eligible])
    value = _minmax([math.log(1.0 / float(m.metrics.cpat_usd.value or 1)) for m in eligible])
    w_q, w_s, w_v = WEIGHTS
    scores: dict[str, float | None] = {m.name: None for m in models}
    for i, m in enumerate(eligible):
        scores[m.name] = 100.0 * (w_q * quality[i] + w_s * speed[i] + w_v * value[i])
    return scores


def _waste_rows(waste: WasteBreakdown) -> list[dict[str, Any]]:
    named = [
        ("Retries", waste.retry),
        ("Excess reasoning", waste.reasoning),
        ("Uncached context", waste.context),
        ("Dead tasks", waste.dead),
    ]
    return [
        {
            "name": name,
            "amount": _usd(component.amount_usd),
            "grade": component.evidence_grade,
            "n": component.n_traces,
        }
        for name, component in named
    ]


def _row(rank: int, m: ModelReport, score: float | None, max_success: float) -> dict[str, Any]:
    met = m.metrics
    success = met.success_rate.value or 0.0
    waste_share = float(m.waste.total_usd / m.total_cost_usd) if m.total_cost_usd else 0.0
    return {
        "rank": rank,
        "name": m.name,
        "score": "—" if score is None else f"{score:.0f}",
        "score_pct": 0 if score is None else round(score),
        "score_class": (
            "low" if score is None or score < 60 else ("mid" if score < 80 else "good")
        ),
        "success": _pct(met.success_rate),
        "success_bar": 0.0 if max_success == 0 else round(success / max_success * 100, 1),
        "cpat": _usd(met.cpat_usd.value),
        "ttat": "—" if met.ttat_seconds.value is None else f"{met.ttat_seconds.value:,.1f}s",
        "attempts": (
            "—" if met.attempts_per_win.value is None else f"{met.attempts_per_win.value:.2f}"
        ),
        "n_verified": met.n_verified,
        "n_unknown": met.n_unknown,
        "n_wins": met.cpat_usd.n_successes,
        "total_cost": _usd(m.total_cost_usd),
        "waste_total": _usd(m.waste.total_usd),
        "waste_share": f"{waste_share * 100:.1f}%",
        "waste_rows": _waste_rows(m.waste),
        "tokens_input": f"{m.tokens_input:,}",
        "tokens_output": f"{m.tokens_output:,}",
        "tokens_reasoning": f"{m.tokens_reasoning:,}",
    }


def render_report(
    *,
    overall: CoreMetrics,
    models: Sequence[ModelReport],
    waste: WasteBreakdown,
    out_path: Path,
    generated_at: datetime | None = None,
) -> Path:
    scores = _scores(models)
    ordered = sorted(models, key=lambda m: scores[m.name] or -1.0, reverse=True)
    max_success = max((m.metrics.success_rate.value or 0.0 for m in models), default=0.0)
    total_cost = sum((m.total_cost_usd for m in models), Decimal("0"))

    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("report.html.j2").render(
        brand=BRAND_NAME,
        grade_name=GRADE_NAME,
        generated_at=(generated_at or datetime.now(tz=UTC)).strftime("%Y-%m-%d %H:%MZ"),
        rows=[_row(i + 1, m, scores[m.name], max_success) for i, m in enumerate(ordered)],
        n_tasks=overall.n_tasks,
        n_verified=overall.n_verified,
        unknown_rate=_pct(overall.unknown_rate),
        unknown_high=(overall.unknown_rate.value or 0.0) > 0.30,
        total_cost=_usd(total_cost),
        cpat=_usd(overall.cpat_usd.value),
        waste_total=_usd(waste.total_usd),
        waste_share=(f"{float(waste.total_usd / total_cost) * 100:.1f}%" if total_cost else "—"),
        n_unpriced=waste.n_unpriced_traces,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
