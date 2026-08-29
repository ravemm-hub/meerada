"""Generic OpenAI-compatible ProviderClient (SPEC §7.3 MATCH).

One client covers every OpenAI-compatible endpoint — OpenAI, Groq, OpenRouter,
DeepSeek, Mistral, Together, local Ollama — which is exactly the free-tier
surface the model landscape research mapped. The HTTP call is the only network
seam (``ChatCaller``); the real impl uses urllib (no dependency), tests inject
a fake. Content resolves from an in-tenant store and never leaves the client.
"""

import json
import time
import urllib.request
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

from handover.replay.anthropic_client import PromptPayload
from handover.replay.runner import ReplayCase, ReplayResult

ContentResolver = Callable[[ReplayCase], PromptPayload]


class ChatCompletion(Protocol):
    text: str
    input_tokens: int
    output_tokens: int


class ChatCaller(Protocol):
    """The single network seam. Real impl posts to a /chat/completions URL."""

    def complete(
        self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> ChatCompletion: ...


class HttpChatCaller:
    """Live caller for any OpenAI-compatible endpoint. Not exercised by tests."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 60.0) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._timeout = timeout

    def complete(
        self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> ChatCompletion:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        }
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self._key}",
                "Content-Type": "application/json",
                "User-Agent": "meerada/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode())

        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]

        class _Result:
            text = str((choice.get("message") or {}).get("content") or "")
            input_tokens = int(usage.get("prompt_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or 0)

        return _Result()


class OpenAICompatClient:
    supports_batch = False

    def __init__(
        self,
        model_id: str,
        caller: ChatCaller,
        resolver: ContentResolver,
        sink: Callable[[ReplayCase, str], str],
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
        output_ref = self._sink(case, completion.text)
        cost = (
            Decimal(completion.input_tokens) * self._price_in
            + Decimal(completion.output_tokens) * self._price_out
        ) / Decimal(1_000_000)
        return ReplayResult(output_ref=output_ref, cost_usd=cost, latency_ms=latency_ms)

    def run_batch(self, cases: list[ReplayCase]) -> list[ReplayResult]:
        return [self.run(case) for case in cases]


# Known OpenAI-compatible base URLs (from the model-landscape research).
ENDPOINTS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
}
