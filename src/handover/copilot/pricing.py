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
