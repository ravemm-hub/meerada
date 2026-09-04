"""Public list prices used to turn a measured task into a measured PRICE.

The grader runs on free tiers (no spend), but a "cost per verified task" has to
be priced at what the model costs at scale — the provider's public list price.
Known prices are marked ``list``; models we can't price yet get a conservative
small-model estimate marked ``estimated`` and the board says so. USD per 1M
tokens (input, output). Update when providers change their pages.
"""

from decimal import Decimal

# model id (substring match, longest wins) -> (in, out, note)
LIST_PRICES: dict[str, tuple[Decimal, Decimal, str]] = {
    # Groq — public pricing page
    "openai/gpt-oss-120b": (Decimal("0.15"), Decimal("0.60"), "list"),
    "openai/gpt-oss-20b": (Decimal("0.075"), Decimal("0.30"), "list"),
    "llama-3.3-70b": (Decimal("0.59"), Decimal("0.79"), "list"),
    "llama-3.1-8b": (Decimal("0.05"), Decimal("0.08"), "list"),
    "llama-4-scout": (Decimal("0.11"), Decimal("0.34"), "list"),
    "llama-4-maverick": (Decimal("0.20"), Decimal("0.60"), "list"),
    "mixtral-8x7b": (Decimal("0.24"), Decimal("0.24"), "list"),
    "gemma2-9b": (Decimal("0.20"), Decimal("0.20"), "list"),
    "kimi-k2": (Decimal("1.00"), Decimal("3.00"), "list"),
    "deepseek-r1-distill-llama-70b": (Decimal("0.75"), Decimal("0.99"), "list"),
    "qwen/qwen3-32b": (Decimal("0.29"), Decimal("0.59"), "list"),
    # newer Qwen3 sizes — priced at the Qwen3-32B list until Groq publishes them
    "qwen/qwen3": (Decimal("0.29"), Decimal("0.59"), "estimated"),
    # compound systems bill the underlying models; priced at gpt-oss-120b level
    "groq/compound": (Decimal("0.15"), Decimal("0.60"), "estimated"),
    "allam-2-7b": (Decimal("0.10"), Decimal("0.30"), "estimated"),
    # Other providers (for when the loop is allowed to grade them)
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60"), "list"),
    "gpt-4o": (Decimal("2.50"), Decimal("10.00"), "list"),
    "claude-3-5-haiku": (Decimal("0.80"), Decimal("4.00"), "list"),
    "claude-3-7-sonnet": (Decimal("3.00"), Decimal("15.00"), "list"),
    "deepseek-chat": (Decimal("0.27"), Decimal("1.10"), "list"),
    "deepseek-reasoner": (Decimal("0.55"), Decimal("2.19"), "list"),
    "mistral-large": (Decimal("2.00"), Decimal("6.00"), "list"),
    "mistral-small": (Decimal("0.10"), Decimal("0.30"), "list"),
}
# A small-model price for anything unknown — labelled as an estimate on the board.
ESTIMATE = (Decimal("0.20"), Decimal("0.60"), "estimated")


def price_for_model(
    model_id: str, live: dict[str, tuple[float, float]] | None = None
) -> tuple[Decimal, Decimal, str]:
    """Price a model for CPAT: the live web catalog (OpenRouter) first — a
    ``:free`` variant is priced at its paid sibling's list price (what it costs
    at scale) — then our static table, then a labelled estimate."""
    live = live or {}
    paid_id = model_id[:-5] if model_id.endswith(":free") else model_id
    for candidate in (paid_id, model_id):
        p = live.get(candidate)
        if p and (p[0] > 0 or p[1] > 0):
            return Decimal(str(p[0])), Decimal(str(p[1])), "list"
    return list_price(paid_id)


def list_price(model_id: str) -> tuple[Decimal, Decimal, str]:
    """Best public price for ``model_id``: longest matching key wins."""
    mid = model_id.lower()
    best = ""
    for key in LIST_PRICES:
        if key in mid and len(key) > len(best):
            best = key
    return LIST_PRICES[best] if best else ESTIMATE
