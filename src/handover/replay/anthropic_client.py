"""Real in-tenant ProviderClient for Anthropic (SPEC §7.3 MATCH).

Resolves ``trace://`` pointers against a local content store, calls the
candidate model, and returns a ReplayResult with a pointer to the stored
output — content never leaves this object. The Anthropic SDK is imported
lazily so the package has no hard dependency and tests never touch the network
(CLAUDE.md: tests use recorded fixtures only).
"""

import time
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any, Protocol

from handover.replay.runner import ReplayCase, ReplayResult

# Resolves a case's input_ref to the in-tenant prompt payload it points at.
ContentResolver = Callable[[ReplayCase], "PromptPayload"]


class PromptPayload:
    """In-tenant prompt content for one replay case. Stays on this machine."""

    def __init__(self, system: str, messages: list[dict[str, str]]) -> None:
        self.system = system
        self.messages = messages


class OutputSink(Protocol):
    """Stores a candidate output in-tenant and returns its trace:// pointer."""

    def put(self, case: ReplayCase, output_text: str) -> str: ...


class _Completion(Protocol):
    text: str
    input_tokens: int
    output_tokens: int


class AnthropicCaller(Protocol):
    """The one network seam. The real impl calls the SDK; tests inject a fake."""

    def complete(
        self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> _Completion: ...


class SdkCaller:
    """Live caller — imports the SDK lazily. Never exercised by tests."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: Any = None

    def _ensure(self) -> Any:
        if self._client is None:
            import anthropic  # lazy: no hard dependency, never imported in tests

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def complete(
        self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> _Completion:
        response = self._ensure().messages.create(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )

        class _Result:
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

        return _Result()


class AnthropicProviderClient:
    """In-tenant replay client. supports_batch is False here; a batch-API
    subclass can override run_batch. Cost is computed from a price table."""

    supports_batch = False

    def __init__(
        self,
        model_id: str,
        caller: AnthropicCaller,
        resolver: ContentResolver,
        sink: OutputSink,
        *,
        price_in_per_mtok: Decimal,
        price_out_per_mtok: Decimal,
        max_tokens: int = 1024,
    ) -> None:
        self.model_id = model_id
        self._caller = caller
        self._resolver = resolver
        self._sink = sink
        self._price_in = price_in_per_mtok
        self._price_out = price_out_per_mtok
        self._max_tokens = max_tokens

    def run(self, case: ReplayCase) -> ReplayResult:
        payload = self._resolver(case)
        start = time.monotonic()
        completion = self._caller.complete(
            self.model_id, payload.system, payload.messages, self._max_tokens
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        output_ref = self._sink.put(case, completion.text)
        cost = (
            Decimal(completion.input_tokens) * self._price_in
            + Decimal(completion.output_tokens) * self._price_out
        ) / Decimal(1_000_000)
        return ReplayResult(output_ref=output_ref, cost_usd=cost, latency_ms=latency_ms)

    def run_batch(self, cases: Any) -> list[ReplayResult]:
        return [self.run(case) for case in cases]


def price_lookup(
    prices: Mapping[str, tuple[Decimal, Decimal]], model_id: str
) -> tuple[Decimal, Decimal]:
    if model_id not in prices:
        raise KeyError(f"no price entry for {model_id}")
    return prices[model_id]
