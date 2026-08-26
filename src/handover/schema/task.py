"""Task — the accounting unit (SPEC.md §3.2)."""

from typing import Literal
from uuid import UUID

from pydantic import NonNegativeInt, PositiveInt

from handover.schema.trace import StrictModel
from handover.schema.types import Money


class TaskTokens(StrictModel):
    input: NonNegativeInt
    output: NonNegativeInt
    reasoning: NonNegativeInt


class Task(StrictModel):
    task_id: UUID
    tenant_id: UUID
    # Clusters exist only from P1 onward; tasks assembled before clustering carry None.
    cluster_id: str | None = None
    attempts: PositiveInt
    succeeded: bool
    first_attempt_success: bool
    total_cost_usd: Money
    total_wall_ms: NonNegativeInt
    total_tokens: TaskTokens
    models_used: tuple[str, ...]
    verification_grade: Literal["measured", "derived", "declared", "unknown"]
