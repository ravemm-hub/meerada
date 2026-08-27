"""In-tenant replay of candidate models over golden cases (SPEC §7.3 MATCH).

Content stays in the tenant: cases carry ``trace://`` pointers, and the
injected provider client resolves them locally. Cost discipline built in:
dedup by input fingerprint, cases ordered by cache key so fixed prefixes hit
the provider's prompt cache, Batch API used when the client supports it, and
every call pre-authorized against the hard daily budget — the runner stops,
it never overruns (P6).
"""

import random
from collections.abc import Callable, Mapping, Sequence
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from handover.metrics.waste import TaskTraces
from handover.pack.goldset import GoldenCase
from handover.replay.budget import DailyBudget

DEFAULT_BATCH_SIZE = 50


class ReplayCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: UUID
    cluster_id: str
    input_ref: str
    expected_ref: str
    verifier_spec: str
    input_fingerprint: str  # dedup key
    cache_key: str  # template fingerprint: groups cases for prompt caching


class ReplayResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    output_ref: str  # tenant-local pointer to the candidate output
    cost_usd: Decimal
    latency_ms: int


class ProviderClient(Protocol):
    """In-tenant client for the candidate model. Tests inject fakes."""

    model_id: str
    supports_batch: bool

    def run(self, case: ReplayCase) -> ReplayResult: ...

    def run_batch(self, cases: Sequence[ReplayCase]) -> list[ReplayResult]: ...


# Programmatic verdict on a replayed case — grade-A verification in-tenant.
CaseVerifier = Callable[[ReplayCase, ReplayResult], bool]


class CaseOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: UUID
    cluster_id: str
    passed: bool | None  # None = never ran (budget stop)
    cost_usd: Decimal
    latency_ms: int
    deduped: bool


class ReplayReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    outcomes: tuple[CaseOutcome, ...]
    total_cost_usd: Decimal
    n_run: int
    n_deduped: int
    n_skipped_budget: int
    budget_stopped: bool


def cases_from_goldset(
    goldset: Sequence[GoldenCase], items: Sequence[TaskTraces]
) -> list[ReplayCase]:
    by_task = {str(item.task.task_id): item for item in items}
    cases = []
    for golden in goldset:
        item = by_task.get(str(golden.case_id))
        if item is None:
            continue
        trace = item.traces[-1]
        cases.append(
            ReplayCase(
                case_id=golden.case_id,
                cluster_id=golden.cluster_id,
                input_ref=golden.input_ref,
                expected_ref=golden.expected_ref,
                verifier_spec=golden.verifier_spec,
                input_fingerprint=trace.input_shape.input_fingerprint,
                cache_key=trace.input_shape.system_prompt_fingerprint,
            )
        )
    return cases


def sample_live_traffic(
    items: Sequence[TaskTraces],
    assignments: Mapping[str, str],
    cost_shares: Mapping[str, float],
    *,
    fraction: float = 0.01,
    seed: int = 42,
) -> list[TaskTraces]:
    """Stratified 1% sample of live tasks, weighted by cluster cost share."""
    by_cluster: dict[str, list[TaskTraces]] = {}
    for item in items:
        cluster_id = assignments.get(str(item.task.task_id))
        if cluster_id is not None:
            by_cluster.setdefault(cluster_id, []).append(item)

    target = max(1, round(fraction * len(items)))
    rng = random.Random(seed)
    sampled: list[TaskTraces] = []
    total_share = sum(cost_shares.get(c, 0.0) for c in by_cluster) or 1.0
    for cluster_id in sorted(by_cluster):
        members = by_cluster[cluster_id]
        share = cost_shares.get(cluster_id, 0.0) / total_share
        quota = min(len(members), max(1, round(target * share)))
        sampled.extend(rng.sample(members, quota))
    return sampled


def replay(
    cases: Sequence[ReplayCase],
    client: ProviderClient,
    verifier: CaseVerifier,
    budget: DailyBudget,
    *,
    estimated_cost_per_case: Decimal = Decimal("0.01"),
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> ReplayReport:
    # Cache locality: group by template so fixed prefixes hit the prompt cache.
    ordered = sorted(cases, key=lambda c: (c.cache_key, str(c.case_id)))

    firsts: dict[str, ReplayCase] = {}
    duplicates: list[ReplayCase] = []
    for case in ordered:
        if case.input_fingerprint in firsts:
            duplicates.append(case)
        else:
            firsts[case.input_fingerprint] = case
    unique = list(firsts.values())

    results: dict[str, tuple[bool, ReplayResult]] = {}  # fingerprint -> verdict
    budget_stopped = False
    n_skipped = 0

    position = 0
    while position < len(unique):
        chunk = unique[position : position + (batch_size if client.supports_batch else 1)]
        if not budget.can_spend(estimated_cost_per_case * len(chunk)):
            if (
                client.supports_batch
                and len(chunk) > 1
                and budget.can_spend(estimated_cost_per_case)
            ):
                chunk = chunk[:1]  # shrink the batch before giving up entirely
            else:
                budget_stopped = True
                n_skipped = len(unique) - position
                break
        chunk_results = client.run_batch(chunk) if client.supports_batch else [client.run(chunk[0])]
        for case, result in zip(chunk, chunk_results, strict=True):
            budget.record(result.cost_usd)
            results[case.input_fingerprint] = (verifier(case, result), result)
        position += len(chunk)
        if budget.remaining() <= 0 and position < len(unique):
            budget_stopped = True
            n_skipped = len(unique) - position
            break

    outcomes: list[CaseOutcome] = []
    for case in ordered:
        hit = results.get(case.input_fingerprint)
        is_duplicate = case in duplicates
        if hit is None:
            outcomes.append(
                CaseOutcome(
                    case_id=case.case_id,
                    cluster_id=case.cluster_id,
                    passed=None,
                    cost_usd=Decimal("0"),
                    latency_ms=0,
                    deduped=False,
                )
            )
            continue
        passed, result = hit
        outcomes.append(
            CaseOutcome(
                case_id=case.case_id,
                cluster_id=case.cluster_id,
                passed=passed,
                cost_usd=Decimal("0") if is_duplicate else result.cost_usd,
                latency_ms=result.latency_ms,
                deduped=is_duplicate,
            )
        )

    return ReplayReport(
        model_id=client.model_id,
        outcomes=tuple(outcomes),
        total_cost_usd=sum((o.cost_usd for o in outcomes), Decimal("0")),
        n_run=len(results),
        n_deduped=len(duplicates),
        n_skipped_budget=n_skipped,
        budget_stopped=budget_stopped,
    )
