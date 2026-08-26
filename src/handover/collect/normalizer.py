"""In-tenant normalization: content-bearing raw events become metadata-only Traces.

The tenant salt enters here and never leaves. Raw content exists only inside
``RawEvent``; nothing in this module logs, stores, or serializes it.
"""

import hashlib
import json
import re
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveInt,
)

from handover.schema.trace import (
    InputShape,
    Latency,
    OutputShape,
    Tokens,
    ToolCall,
    Trace,
    Verification,
)

# A trace whose source carried no verification signal (SPEC §3.2 rule 4).
UNVERIFIED = Verification(
    status="unknown",
    method="programmatic",
    signal="none",
    confidence=0.0,
    evidence_grade="declared",
)


class RawMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str = ""


class RawToolCall(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    args: Any = None
    ts_offset_ms: NonNegativeInt = 0
    duration_ms: NonNegativeInt = 0
    status: str = "ok"


class RawTokens(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: NonNegativeInt = 0
    input_cached: NonNegativeInt = 0
    output: NonNegativeInt = 0
    reasoning: NonNegativeInt = 0


class RawEvent(BaseModel):
    """A provider event as captured in the tenant environment. Content-bearing."""

    model_config = ConfigDict(extra="ignore")

    provider: str
    model_id: str
    model_version_hint: str = "unknown"
    endpoint_region: str = "unknown"

    ts_start: AwareDatetime
    ts_end: AwareDatetime

    messages: list[RawMessage] = Field(default_factory=list)
    output_text: str = ""
    has_attachments: bool = False

    tokens: RawTokens = Field(default_factory=RawTokens)
    cost_usd: Decimal = Decimal("0")
    ttft_ms: NonNegativeInt = 0
    total_ms: NonNegativeInt = 0

    tool_calls: list[RawToolCall] = Field(default_factory=list)

    session_id: str | None = None
    trace_id: UUID | None = None
    task_id: UUID | None = None
    attempt_no: PositiveInt = 1
    verification: Verification | None = None


# Substituted variables are replaced with placeholders before hashing the system
# prompt, so the fingerprint identifies the *template* (SPEC §3.1 notes).
_VARIABLE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I),
        "<uuid>",
    ),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}([T ][\d:.]+Z?)?"), "<ts>"),
    (re.compile(r"\d+"), "<n>"),
)

_CODE_BLOCK = re.compile(r"```.*?```", re.S)


def strip_variables(text: str) -> str:
    for pattern, placeholder in _VARIABLE_PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


def _json_skeleton(value: object) -> object:
    """Structure of a JSON value with all content removed: keys and types only."""
    if isinstance(value, dict):
        return {key: _json_skeleton(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_json_skeleton(value[0])] if value else []
    return type(value).__name__


class Hasher:
    """Salted SHA-256 fingerprints. The salt is tenant config and never leaves."""

    def __init__(self, salt: str) -> None:
        self._salt = salt.encode()

    def fingerprint(self, text: str) -> str:
        return "sha256:" + hashlib.sha256(self._salt + text.encode()).hexdigest()

    def __repr__(self) -> str:
        return "Hasher(salt=<redacted>)"


class Normalizer:
    """Converts RawEvent (content) into Trace (metadata only)."""

    def __init__(self, tenant_id: UUID, salt: str) -> None:
        self._tenant_id = tenant_id
        self._hasher = Hasher(salt)

    def normalize(self, raw: RawEvent) -> Trace:
        system_text = next((m.content for m in raw.messages if m.role == "system"), "")
        input_text = "\n".join(f"{m.role}:{m.content}" for m in raw.messages)

        total_ms = raw.total_ms or max(0, int((raw.ts_end - raw.ts_start).total_seconds() * 1000))

        return Trace(
            trace_id=raw.trace_id or uuid4(),
            tenant_id=self._tenant_id,
            task_id=raw.task_id or uuid4(),
            attempt_no=raw.attempt_no,
            ts_start=raw.ts_start,
            ts_end=raw.ts_end,
            provider=raw.provider,
            model_id=raw.model_id,
            model_version_hint=raw.model_version_hint,
            endpoint_region=raw.endpoint_region,
            tokens=Tokens(
                input=raw.tokens.input,
                input_cached=raw.tokens.input_cached,
                output=raw.tokens.output,
                reasoning=raw.tokens.reasoning,
            ),
            cost_usd=raw.cost_usd,
            latency=Latency(ttft_ms=raw.ttft_ms, total_ms=total_ms),
            input_shape=InputShape(
                n_messages=len(raw.messages),
                n_chars=sum(len(m.content) for m in raw.messages),
                has_attachments=raw.has_attachments,
                system_prompt_fingerprint=self._hasher.fingerprint(strip_variables(system_text)),
                input_fingerprint=self._hasher.fingerprint(input_text),
            ),
            output_shape=self._output_shape(raw.output_text),
            tool_calls=tuple(
                ToolCall(
                    name=call.name,
                    args_fingerprint=self._hasher.fingerprint(
                        json.dumps(call.args, sort_keys=True, default=str)
                    ),
                    ts_offset_ms=call.ts_offset_ms,
                    duration_ms=call.duration_ms,
                    status=call.status,
                )
                for call in raw.tool_calls
            ),
            verification=raw.verification or UNVERIFIED,
        )

    def _output_shape(self, text: str) -> OutputShape:
        json_valid = False
        schema_fingerprint: str | None = None
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        else:
            json_valid = True
            skeleton = json.dumps(_json_skeleton(parsed), sort_keys=True)
            schema_fingerprint = self._hasher.fingerprint(skeleton)

        code_blocks = _CODE_BLOCK.findall(text)
        n_code_blocks = len(code_blocks)

        output_type: Literal["json", "text", "code", "mixed"]
        if json_valid:
            output_type = "json"
        elif n_code_blocks > 0:
            outside = _CODE_BLOCK.sub("", text).strip()
            output_type = "code" if not outside else "mixed"
        else:
            output_type = "text"

        return OutputShape(
            type=output_type,
            n_chars=len(text),
            json_valid=json_valid,
            schema_fingerprint=schema_fingerprint,
            has_code_block=n_code_blocks > 0,
            n_code_blocks=n_code_blocks,
        )
