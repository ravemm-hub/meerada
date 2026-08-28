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

# Content-typed identifier fields. These are the free-text fields that would
# otherwise ship in a pack/report; constraining them at the schema means a
# Trace carrying content in them fails validation and never enters the system
# (preventive, not merely detected at export). No interior whitespace, bounded
# length — enough for real model ids / tool names / signals, too little for
# smuggled content.
Slug = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9](?:[\w.:/+-]{0,127})$")]
# Signals are enum-like lowercase tokens (test_exit_code, silent_acceptance...).
Signal = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,64}$")]
# A short status word (ok, error, timeout...).
Status = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,32}$")]
# Region: identifier or the literal "unknown".
Region = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


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
    name: Slug
    args_fingerprint: Fingerprint
    ts_offset_ms: NonNegativeInt
    duration_ms: NonNegativeInt
    status: Status


class Verification(StrictModel):
    status: Literal["pass", "fail", "unknown"]
    method: Literal["programmatic", "downstream", "judge"]
    signal: Signal
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    evidence_grade: Literal["measured", "derived", "declared"]


class Trace(StrictModel):
    trace_id: UUID
    tenant_id: UUID
    task_id: UUID
    attempt_no: PositiveInt

    ts_start: AwareDatetime
    ts_end: AwareDatetime

    provider: Slug
    model_id: Slug
    model_version_hint: Slug
    endpoint_region: Region

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
