"""The monthly receipt (SPEC P3): spend vs delivered verified tasks, waste
breakdown, and a routing RECOMMENDATION — we recommend, we never route (P
principle: independence). One self-contained HTML file for the CFO."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, ConfigDict

from handover.branding import BRAND_NAME
from handover.metrics import CoreMetrics, WasteBreakdown
from handover.report.renderer import ModelReport, _pct, _usd

MAX_QUALITY_DROP_POINTS = 2.0


class RoutingRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str  # "move" | "stay"
    from_model: str | None
    to_model: str | None
    est_monthly_savings_usd: Decimal | None
    quality_delta_points: float | None
    note: str  # always labelled as a derived estimate


def routing_recommendation(models: Sequence[ModelReport]) -> RoutingRecommendation:
    """Recommend moving spend to the best-value model whose verified quality is
    within 2 points of the current one. Estimate, clearly labelled — never routed."""
    eligible = [
        m for m in models if m.metrics.cpat_usd.value and m.metrics.success_rate.value is not None
    ]
    if len(eligible) < 2:
        return RoutingRecommendation(
            kind="stay",
            from_model=None,
            to_model=None,
            est_monthly_savings_usd=None,
            quality_delta_points=None,
            note="fewer than two comparable models in this period",
        )
    spender = max(eligible, key=lambda m: m.total_cost_usd)
    best_value = min(eligible, key=lambda m: m.metrics.cpat_usd.value or Decimal(0))
    if best_value.name == spender.name:
        return RoutingRecommendation(
            kind="stay",
            from_model=spender.name,
            to_model=None,
            est_monthly_savings_usd=None,
            quality_delta_points=None,
            note="your largest spend already sits on the best-value model",
        )
    quality_delta = (
        (best_value.metrics.success_rate.value or 0) - (spender.metrics.success_rate.value or 0)
    ) * 100
    if quality_delta < -MAX_QUALITY_DROP_POINTS:
        return RoutingRecommendation(
            kind="stay",
            from_model=spender.name,
            to_model=best_value.name,
            est_monthly_savings_usd=None,
            quality_delta_points=round(quality_delta, 1),
            note=(
                f"cheaper model {best_value.name} drops verified quality by "
                f"{abs(quality_delta):.1f} points — not recommended without a Handshake"
            ),
        )
    spender_cpat = spender.metrics.cpat_usd.value or Decimal(0)
    best_cpat = best_value.metrics.cpat_usd.value or Decimal(0)
    savings = (spender_cpat - best_cpat) * spender.metrics.cpat_usd.n_successes
    return RoutingRecommendation(
        kind="move",
        from_model=spender.name,
        to_model=best_value.name,
        est_monthly_savings_usd=savings,
        quality_delta_points=round(quality_delta, 1),
        note=(
            "derived estimate from this period's verified tasks; "
            "validate via a Handshake gap report"
        ),
    )


def render_receipt(
    *,
    period: str,  # e.g. "2026-08"
    overall: CoreMetrics,
    models: Sequence[ModelReport],
    waste: WasteBreakdown,
    out_path: Path,
    generated_at: datetime | None = None,
) -> Path:
    recommendation = routing_recommendation(models)
    total_spend = sum((m.total_cost_usd for m in models), Decimal("0"))
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("receipt.html.j2").render(
        brand=BRAND_NAME,
        period=period,
        generated_at=(generated_at or datetime.now(tz=UTC)).strftime("%Y-%m-%d %H:%MZ"),
        total_spend=_usd(total_spend),
        delivered=overall.cpat_usd.n_successes,
        n_verified=overall.n_verified,
        n_tasks=overall.n_tasks,
        cpat=_usd(overall.cpat_usd.value),
        unknown_rate=_pct(overall.unknown_rate),
        waste_total=_usd(waste.total_usd),
        waste_share=(f"{float(waste.total_usd / total_spend) * 100:.1f}%" if total_spend else "—"),
        waste_rows=[
            {"name": name, "amount": _usd(component.amount_usd), "grade": component.evidence_grade}
            for name, component in [
                ("Retries", waste.retry),
                ("Excess reasoning", waste.reasoning),
                ("Uncached context", waste.context),
                ("Dead tasks", waste.dead),
            ]
        ],
        model_rows=[
            {
                "name": m.name,
                "spend": _usd(m.total_cost_usd),
                "delivered": m.metrics.cpat_usd.n_successes,
                "cpat": _usd(m.metrics.cpat_usd.value),
                "success": _pct(m.metrics.success_rate),
            }
            for m in sorted(models, key=lambda m: m.total_cost_usd, reverse=True)
        ],
        rec=recommendation,
        rec_savings=_usd(recommendation.est_monthly_savings_usd),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
