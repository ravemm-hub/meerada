"""Waste decomposition (SPEC §4.2).

Retry and dead waste are sums of actual recorded cost: ``measured``.
Reasoning and context waste are estimates against a counterfactual: ``derived``
— any report must label them as such. Tasks graded "unknown" are excluded.

Clusters do not exist until P1, so the reasoning baseline (p50 of successful
attempts) is computed per system-prompt template fingerprint — the P0 proxy
for a task cluster.
"""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from statistics import median
from typing import Literal

from pydantic import BaseModel, ConfigDict

from handover.schema.task import Task
from handover.schema.trace import Trace

MTOK = Decimal(1_000_000)


class ModelPrice(BaseModel):
    """USD per million tokens."""

    model_config = ConfigDict(frozen=True)

    input_per_mtok: Decimal
    output_per_mtok: Decimal


class TaskTraces(BaseModel):
    model_config = ConfigDict(frozen=True)

    task: Task
    traces: tuple[Trace, ...]


class WasteComponent(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount_usd: Decimal
    evidence_grade: Literal["measured", "derived"]
    n_traces: int


class WasteBreakdown(BaseModel):
    model_config = ConfigDict(frozen=True)

    retry: WasteComponent
    reasoning: WasteComponent
    context: WasteComponent
    dead: WasteComponent
    n_unpriced_traces: int
    total_usd: Decimal


def _reasoning_baselines(items: Sequence[TaskTraces]) -> dict[str, int]:
    """p50 reasoning tokens of successful attempts, per template fingerprint."""
    per_template: dict[str, list[int]] = {}
    for item in items:
        for trace in item.traces:
            if trace.verification.status == "pass":
                fingerprint = trace.input_shape.system_prompt_fingerprint
                per_template.setdefault(fingerprint, []).append(trace.tokens.reasoning)
    return {fp: int(median(values)) for fp, values in per_template.items()}


def compute_waste(items: Sequence[TaskTraces], prices: Mapping[str, ModelPrice]) -> WasteBreakdown:
    verified = [item for item in items if item.task.verification_grade != "unknown"]
    baselines = _reasoning_baselines(verified)
    unpriced: set[str] = set()

    retry_usd = Decimal("0")
    retry_n = 0
    dead_usd = Decimal("0")
    dead_n = 0
    reasoning_usd = Decimal("0")
    reasoning_n = 0
    context_usd = Decimal("0")
    context_n = 0

    seen_templates: set[str] = set()
    all_traces = sorted(
        (trace for item in verified for trace in item.traces),
        key=lambda t: t.ts_start,
    )

    for item in verified:
        if item.task.succeeded:
            for trace in item.traces:
                if trace.verification.status == "fail":
                    retry_usd += trace.cost_usd
                    retry_n += 1
        else:
            dead_usd += item.task.total_cost_usd
            dead_n += len(item.traces)

        for trace in item.traces:
            baseline = baselines.get(trace.input_shape.system_prompt_fingerprint)
            if baseline is None or trace.tokens.reasoning <= baseline:
                continue
            price = prices.get(trace.model_id)
            if price is None:
                unpriced.add(str(trace.trace_id))
                continue
            excess = trace.tokens.reasoning - baseline
            reasoning_usd += Decimal(excess) / MTOK * price.output_per_mtok
            reasoning_n += 1

    for trace in all_traces:
        fingerprint = trace.input_shape.system_prompt_fingerprint
        if fingerprint not in seen_templates:
            seen_templates.add(fingerprint)  # first occurrence: nothing to cache yet
            continue
        uncached = trace.tokens.input - trace.tokens.input_cached
        if uncached <= 0:
            continue
        price = prices.get(trace.model_id)
        if price is None:
            unpriced.add(str(trace.trace_id))
            continue
        context_usd += Decimal(uncached) / MTOK * price.input_per_mtok
        context_n += 1

    return WasteBreakdown(
        retry=WasteComponent(amount_usd=retry_usd, evidence_grade="measured", n_traces=retry_n),
        reasoning=WasteComponent(
            amount_usd=reasoning_usd, evidence_grade="derived", n_traces=reasoning_n
        ),
        context=WasteComponent(
            amount_usd=context_usd, evidence_grade="derived", n_traces=context_n
        ),
        dead=WasteComponent(amount_usd=dead_usd, evidence_grade="measured", n_traces=dead_n),
        n_unpriced_traces=len(unpriced),
        total_usd=retry_usd + reasoning_usd + context_usd + dead_usd,
    )
