"""Build ChatCaller instances from environment keys — free-tier by default.

Keys are read from the environment only (never files), matching the scheduled
grader. This is the one place the Copilot touches provider credentials.
"""

import os

from handover.replay.openai_client import ENDPOINTS, ChatCaller, HttpChatCaller

ENV_KEYS: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
}


def caller_for_provider(provider: str) -> ChatCaller:
    """Live caller for ``provider``; raises if its key or endpoint is missing."""
    if provider not in ENDPOINTS:
        raise RuntimeError(f"unknown provider {provider!r} (known: {', '.join(sorted(ENDPOINTS))})")
    env = ENV_KEYS.get(provider, "")
    key = os.environ.get(env, "").strip()
    if not key:
        raise RuntimeError(f"no API key for {provider} — set {env}")
    return HttpChatCaller(ENDPOINTS[provider], key)
