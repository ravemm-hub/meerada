"""Build ChatCaller instances from provider keys.

Most providers speak the OpenAI-compatible protocol (one HTTP seam). Anthropic
(Claude) is native (/v1/messages), so it gets its own caller. ``build_caller``
is the single place that maps a provider + key to the right caller — used by the
desktop key vault and by env-based callers alike. Keys are used only to talk to
the provider; they are never logged.
"""

import json
import os
import urllib.request

from handover.replay.openai_client import ENDPOINTS, ChatCaller, ChatCompletion, HttpChatCaller

ENV_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class AnthropicChatCaller:
    """ChatCaller for Anthropic's native Messages API (not OpenAI-compatible)."""

    def __init__(self, api_key: str, timeout: float = 90.0) -> None:
        self._key = api_key
        self._timeout = timeout

    def complete(
        self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> ChatCompletion:
        body: dict[str, object] = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            body["system"] = system
        request = urllib.request.Request(
            ANTHROPIC_URL,
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": self._key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "User-Agent": "meerada/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as resp:
            data = json.loads(resp.read().decode())
        usage = data.get("usage") or {}
        blocks = data.get("content") or []

        class _Result:
            text = "".join(
                str(b.get("text") or "") for b in blocks if b.get("type") == "text"
            )
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)

        return _Result()


def build_caller(provider: str, key: str) -> ChatCaller:
    """The right caller for a provider + key (Anthropic native, else OpenAI-compat)."""
    if not key:
        raise RuntimeError(f"no key for {provider}")
    if provider == "anthropic":
        return AnthropicChatCaller(key)
    if provider in ENDPOINTS:
        return HttpChatCaller(ENDPOINTS[provider], key)
    raise RuntimeError(f"unknown provider {provider!r}")


def caller_for_provider(provider: str) -> ChatCaller:
    """Live caller for ``provider`` from its environment key; raises if missing."""
    env = ENV_KEYS.get(provider, "")
    key = os.environ.get(env, "").strip()
    if not key:
        raise RuntimeError(f"no API key for {provider} — set {env}")
    return build_caller(provider, key)
