"""Per-model token prices for real cost analysis (USD per million tokens).

Approximate public list prices, matched by model-id substring with the first
match winning, then a provider fallback. Used to turn token counts into real
dollars and CPAT (cost per accepted task) in the Manager. Free-tier ids (Groq
open models) resolve to $0, so cost analysis is honest there too. This table is
the one place to maintain prices; a production build would refresh it from the
live catalog.
"""

from decimal import Decimal

# (input, output) USD per 1M tokens. First substring match wins, so put the more
# specific ids before the generic family fallback.
_TABLE: tuple[tuple[str, tuple[str, str]], ...] = (
    # 2026-09 list prices (OpenRouter feed / vendor pages)
    ("gpt-6-astra", ("10", "50")),
    ("gpt-5.6-terra", ("2", "12")),
    ("gpt-5.6-luna", ("0.2", "1.2")),
    ("gpt-5.6-sol", ("2", "12")),
    ("gpt-5.4-nano", ("0.05", "0.4")),
    ("gpt-5.4-mini", ("0.25", "2")),
    ("gpt-5.3-codex", ("1.25", "10")),
    ("gpt-4.1-mini", ("0.4", "1.6")),
    ("gpt-4.1", ("2", "8")),
    ("claude-fable", ("10", "50")),
    ("claude-sonnet-5", ("2", "10")),
    ("claude-haiku-4-5", ("1", "5")),
    ("gemini-3.8-flash", ("0.75", "3.75")),
    ("gemini-2.5-flash", ("0.3", "2.5")),
    ("grok-4.6", ("2", "6")),
    ("deepseek-v4-pro", ("0.87", "1.74")),
    ("deepseek-v4-flash", ("0.086", "0.17")),
    ("glm-5.3-flash", ("0.075", "0.25")),
    ("muse-spark", ("1.25", "4.25")),
    ("qwen3.8-max", ("2", "6")),
    ("qwen3.8-flash", ("0.15", "0.47")),
    ("kimi-k3", ("3", "15")),
    ("minimax-m3", ("0.3", "1.2")),
    ("mistral-medium", ("1.5", "7.5")),
    ("mistral-small", ("0.15", "0.6")),
    ("codestral", ("0.3", "0.9")),
    ("claude-opus", ("5", "25")),
    ("claude-sonnet", ("3", "15")),
    ("claude-haiku", ("0.8", "4")),
    ("claude", ("3", "15")),
    ("gpt-oss", ("0", "0")),  # Groq-hosted open models, free tier
    ("gpt-4o-mini", ("0.15", "0.6")),
    ("gpt-4o", ("2.5", "10")),
    ("gpt-5", ("5", "15")),
    ("gpt", ("2", "8")),
    ("o3", ("2", "8")),
    ("gemini-2.5-pro", ("1.25", "10")),
    ("gemini-1.5-pro", ("1.25", "5")),
    ("gemini", ("0.3", "2.5")),
    ("deepseek", ("0.27", "1.10")),
    ("qwen", ("0", "0")),  # Groq free tier
    ("compound", ("0", "0")),
    ("llama", ("0", "0")),
    ("gemma", ("0", "0")),
    ("mistral", ("0.4", "2")),
    ("mixtral", ("0.4", "2")),
    ("grok", ("2", "10")),
)
_DEFAULT = (Decimal("0"), Decimal("0"))


def price_for(model_id: str) -> tuple[Decimal, Decimal]:
    """(input, output) USD per million tokens for a model id; $0 if unknown/free."""
    low = model_id.lower()
    for needle, (price_in, price_out) in _TABLE:
        if needle in low:
            return Decimal(price_in), Decimal(price_out)
    return _DEFAULT
