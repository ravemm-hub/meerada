"""Synthetic raw-event generator for the P0 acceptance run.

Three models with distinct cost/quality profiles, twelve prompt templates,
realistic retry patterns, and a slice of unverified traffic. Deterministic.
"""

import random
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from handover.assemble import AttemptRecord
from handover.collect import Normalizer, RawEvent
from tests.factories import T0

# (input $/Mtok, output $/Mtok, first-try success rate, reasoning burn 0..1)
PROFILES = {
    "model-alpha": (Decimal("3"), Decimal("15"), 0.90, 0.2),
    "model-beta": (Decimal("1.1"), Decimal("4.4"), 0.82, 0.6),
    "model-gamma": (Decimal("0.3"), Decimal("1.2"), 0.70, 0.9),
}
# Letters, not digits: strip_variables() replaces digits, which would collapse
# every numbered template into one fingerprint.
TEMPLATES = [f"template {chr(65 + i)}" for i in range(12)]


def _raw_event(
    rng: random.Random,
    *,
    model: str,
    template: str,
    session: str,
    start_s: int,
    status: str | None,
) -> RawEvent:
    price_in, price_out, _, burn = PROFILES[model]
    input_tokens = rng.randint(2_000, 20_000)
    cached = int(input_tokens * rng.uniform(0.0, 0.7))
    output_tokens = rng.randint(200, 3_000)
    reasoning = int(rng.uniform(0, 4_000) * burn)
    cost = (
        Decimal(input_tokens - cached) * price_in
        + Decimal(cached) * price_in / 10
        + Decimal(output_tokens + reasoning) * price_out
    ) / Decimal(1_000_000)
    duration = rng.randint(5, 90)
    verification = None
    if status is not None:
        verification = {
            "status": status,
            "method": "programmatic",
            "signal": "test_exit_code",
            "confidence": 1.0,
            "evidence_grade": "measured",
        }
    return RawEvent.model_validate(
        {
            "provider": "synthetic",
            "model_id": model,
            "ts_start": (T0 + timedelta(seconds=start_s)).isoformat(),
            "ts_end": (T0 + timedelta(seconds=start_s + duration)).isoformat(),
            "messages": [
                {"role": "system", "content": f"You are the worker for {template}."},
                {"role": "user", "content": f"do the thing, variant {rng.randint(0, 9999)}"},
            ],
            "output_text": '{"ok": true}' if rng.random() < 0.6 else "plain text answer",
            "tokens": {
                "input": input_tokens,
                "input_cached": cached,
                "output": output_tokens,
                "reasoning": reasoning,
            },
            "cost_usd": str(cost.quantize(Decimal("0.000001"))),
            "session_id": session,
            "verification": verification,
        }
    )


def generate_records(n_traces: int = 10_000, seed: int = 42) -> list[AttemptRecord]:
    rng = random.Random(seed)
    normalizer = Normalizer(tenant_id=UUID(int=1), salt="synthetic-salt")
    records: list[AttemptRecord] = []
    clock = 0
    task_index = 0

    while len(records) < n_traces:
        task_index += 1
        model = rng.choice(list(PROFILES))
        template = rng.choice(TEMPLATES)
        session = f"session-{task_index}"
        first_try = PROFILES[model][2]

        roll = rng.random()
        if roll < 0.07:
            statuses: list[str | None] = [None]  # no verification signal
        elif roll < 0.15:
            statuses = ["fail"] * rng.choice([1, 2, 3])  # dead task
        elif rng.random() < first_try:
            statuses = ["pass"]
        else:
            statuses = ["fail"] * rng.choice([1, 2]) + ["pass"]  # retry then win

        start = clock
        for status in statuses:
            raw = _raw_event(
                rng, model=model, template=template, session=session, start_s=start, status=status
            )
            records.append(
                AttemptRecord(
                    trace=normalizer.normalize(raw),
                    session_id=raw.session_id,
                    explicit_task_id=None,
                )
            )
            start += rng.randint(30, 110)
        clock += 400  # keep distinct tasks safely outside the 120s window

    return records[:n_traces]
