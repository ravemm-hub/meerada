"""Trace — the atomic record (SPEC.md §3.1).

Metadata only. No content field exists in this schema, and ``extra="forbid"``
rejects any attempt to smuggle one in.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
    StringConstraints,
    model_validator,
)

from handover.schema.types import Money

SCHEMA_VERSION = "1.0"

Fingerprint = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    """Base for all boundary models: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Tokens(StrictModel):
    input: NonNegativeInt
    input_cached: NonNegativeInt
    output: NonNegativeInt
    reasoning: NonNegativeInt


class Latency(StrictModel):
    ttft_ms: NonNegativeInt
    total_ms: NonNegativeInt


class InputShape(StrictModel):
    n_messages: NonNegativeInt
    n_chars: NonNegativeInt
    has_attachments: bool
    system_prompt_fingerprint: Fingerprint
    input_fingerprint: Fingerprint


class OutputShape(StrictModel):
    type: Literal["json", "text", "code", "mixed"]
    n_chars: NonNegativeInt
    json_valid: bool
    schema_fingerprint: Fingerprint | None
    has_code_block: bool
    n_code_blocks: NonNegativeInt


class ToolCall(StrictModel):
    name: str
    args_fingerprint: Fingerprint
    ts_offset_ms: NonNegativeInt
    duration_ms: NonNegativeInt
    status: str


class Verification(StrictModel):
    status: Literal["pass", "fail", "unknown"]
    method: Literal["programmatic", "downstream", "judge"]
    signal: str
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence_grade: Literal["measured", "derived", "declared"]


class Trace(StrictModel):
    trace_id: UUID
    tenant_id: UUID
    task_id: UUID
    attempt_no: PositiveInt

    ts_start: AwareDatetime
    ts_end: AwareDatetime

    provider: str
    model_id: str
    model_version_hint: str
    endpoint_region: str

    tokens: Tokens
    cost_usd: Money

    latency: Latency

    input_shape: InputShape
    output_shape: OutputShape

    tool_calls: tuple[ToolCall, ...] = ()

    verification: Verification

    redaction_level: Literal["metadata_only"] = "metadata_only"
    schema_version: str = SCHEMA_VERSION

    @model_validator(mode="after")
    def _end_not_before_start(self) -> "Trace":
        if self.ts_end < self.ts_start:
            raise ValueError("ts_end must not precede ts_start")
        return self
