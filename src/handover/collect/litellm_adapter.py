"""LiteLLM custom-logger callback that feeds normalized Traces to a sink.

Duck-typed against LiteLLM's success/failure callback contract; ``litellm`` is
deliberately not a dependency — tests use recorded payloads (CLAUDE.md rule:
tests never call a live model API).
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from handover.collect.normalizer import (
    Normalizer,
    RawEvent,
    RawMessage,
    RawTokens,
)
from handover.schema.trace import Trace, Verification

API_FAILURE = Verification(
    status="fail",
    method="programmatic",
    signal="api_error",
    confidence=1.0,
    evidence_grade="measured",
)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Field access that works for both dict payloads and response objects."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


class LiteLLMAdapter:
    """Register an instance as a LiteLLM custom logger; traces flow to ``sink``."""

    def __init__(self, normalizer: Normalizer, sink: Callable[[Trace], None]) -> None:
        self._normalizer = normalizer
        self._sink = sink

    def log_success_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        raw = self._to_raw(kwargs, response_obj, start_time, end_time, failed=False)
        self._sink(self._normalizer.normalize(raw))

    def log_failure_event(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        raw = self._to_raw(kwargs, response_obj, start_time, end_time, failed=True)
        self._sink(self._normalizer.normalize(raw))

    def _to_raw(
        self,
        kwargs: dict[str, Any],
        response_obj: Any,
        start_time: datetime,
        end_time: datetime,
        failed: bool,
    ) -> RawEvent:
        messages = [
            RawMessage(role=str(_get(m, "role", "user")), content=str(_get(m, "content") or ""))
            for m in kwargs.get("messages") or []
        ]

        usage = _get(response_obj, "usage")
        prompt_details = _get(usage, "prompt_tokens_details")
        completion_details = _get(usage, "completion_tokens_details")
        tokens = RawTokens(
            input=int(_get(usage, "prompt_tokens", 0) or 0),
            input_cached=int(_get(prompt_details, "cached_tokens", 0) or 0),
            output=int(_get(usage, "completion_tokens", 0) or 0),
            reasoning=int(_get(completion_details, "reasoning_tokens", 0) or 0),
        )

        choices = _get(response_obj, "choices") or []
        first_message = _get(choices[0], "message") if choices else None
        output_text = str(_get(first_message, "content") or "")

        cost = kwargs.get("response_cost")

        return RawEvent(
            provider=str(kwargs.get("custom_llm_provider") or "unknown"),
            model_id=str(kwargs.get("model") or "unknown"),
            ts_start=_aware(start_time),
            ts_end=_aware(end_time),
            messages=messages,
            output_text=output_text,
            tokens=tokens,
            cost_usd=Decimal(str(cost)) if cost is not None else Decimal("0"),
            session_id=str(kwargs.get("litellm_session_id") or "") or None,
            verification=API_FAILURE if failed else None,
        )
