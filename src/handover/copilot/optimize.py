"""Copilot prompt optimizer — the translator between a user's plain words and a
model-efficient prompt (SPEC §7.3 TRANSLATE, applied live at the point of use).

Deterministic and offline: given a plain-language intent it strips filler,
imposes a contract-first structure, and applies the target model's prompting
conventions — then reports the token saving against the verbose prompt a user
would naively send. No network, no model call: this is the local rewrite that
runs before every request the Copilot routes, so it is fully testable.
"""

import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

# Structural conventions per model family (mirrors migrate.translator.TARGET_HINTS,
# applied here as structure rather than as a hint handed to another model).
_CONVENTION: dict[str, str] = {
    "claude": "role and constraints first, tagged structure, positive instructions",
    "gpt": "concise system, fenced schema, explicit refusal rules",
    "gemini": "short declarative instruction, restate the format at the end",
}
_DEFAULT_CONVENTION = "explicit output contract, no preamble"

# The bloat a beginner pastes in front of every request — the honest baseline the
# saving is measured against.
NAIVE_PREAMBLE = (
    "You are an extremely helpful, thorough and knowledgeable AI assistant. "
    "Please think carefully and reason step by step, explain your reasoning in "
    "detail, be as complete and comprehensive as possible, and always double-check "
    "your work before you answer. Here is what I need you to do: "
)
NAIVE_SUFFIX = " Please make sure to explain everything thoroughly and completely."

# Filler that adds tokens without changing the instruction.
_FILLER = re.compile(
    r"\b(please|kindly|could you|can you|would you|i would like you to|"
    r"i want you to|i need you to|for me|as an ai|if possible|thank you|thanks|"
    r"just|really|very|basically|actually)\b",
    re.I,
)
_WS = re.compile(r"\s+")
_JSON_HINT = re.compile(r"\b(json|fields?|extract|schema|object|list of|table|csv)\b", re.I)


def est_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate (~4 chars/token)."""
    return max(1, round(len(text) / 4))


def _convention_for(model: str) -> str:
    low = model.lower()
    for key, conv in _CONVENTION.items():
        if key in low:
            return conv
    return _DEFAULT_CONVENTION


def _compress(intent: str) -> str:
    return _WS.sub(" ", _FILLER.sub("", intent)).strip(" .,\t\n").strip()


class OptimizedPrompt(BaseModel):
    """A ready-to-send lean prompt plus the saving vs the naive baseline."""

    model_config = ConfigDict(frozen=True)

    target_model: str
    system: str
    user: str
    convention: str
    naive_text: str
    naive_tokens: int
    optimized_tokens: int
    saved_tokens: int
    saved_pct: int

    def cost_saved(self, price_in_per_mtok: Decimal) -> Decimal:
        """Input-cost saved on one call at the given price per Mtok."""
        return (Decimal(self.saved_tokens) * price_in_per_mtok) / Decimal(1_000_000)


def optimize(intent: str, target_model: str = "claude") -> OptimizedPrompt:
    """Rewrite a plain-language ``intent`` into a lean prompt for ``target_model``."""
    core = _compress(intent) or intent.strip()
    convention = _convention_for(target_model)
    if _JSON_HINT.search(intent):
        system = f"Return ONLY valid JSON, no prose. Style: {convention}."
    else:
        system = f"Answer directly in one pass, no preamble. Style: {convention}."
    user = (core[0].upper() + core[1:]).rstrip(".") + "." if core else ""

    naive_text = NAIVE_PREAMBLE + intent.strip() + NAIVE_SUFFIX
    naive_tokens = est_tokens(naive_text)
    optimized_tokens = est_tokens(system + " " + user)
    saved = max(0, naive_tokens - optimized_tokens)
    pct = round(saved / naive_tokens * 100) if naive_tokens else 0
    return OptimizedPrompt(
        target_model=target_model,
        system=system,
        user=user,
        convention=convention,
        naive_text=naive_text,
        naive_tokens=naive_tokens,
        optimized_tokens=optimized_tokens,
        saved_tokens=saved,
        saved_pct=pct,
    )
