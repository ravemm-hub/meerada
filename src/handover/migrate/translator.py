"""Prompt translation for the target model's conventions (SPEC §7.3 TRANSLATE).

Produces DRAFTS for human review: a unified diff plus a rationale per change.
Nothing here writes prompts anywhere — ``applied`` is always False and there is
no apply function in this module. Model calls are injected and pre-authorized
against a hard budget (P6).
"""

import difflib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from handover.cluster.labeler import SpendBudget
from handover.pack.contract import OutputContract
from handover.pack.tool_policy import ToolPolicy

TARGET_HINTS: dict[str, str] = {
    "claude": (
        "Claude conventions: put role and constraints up front; use XML-style tags for "
        "structure; state the output contract explicitly; prefer positive instructions."
    ),
    "gpt": (
        "OpenAI GPT conventions: concise system message; use markdown headers for "
        "sections; put the output schema in a fenced block; explicit refusal rules."
    ),
    "gemini": (
        "Gemini conventions: short declarative system instruction; enumerate steps; "
        "restate the output format at the end."
    ),
}
_DEFAULT_HINT = "General conventions: be explicit about the output contract and tool order."


class TranslationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    cost_usd: Decimal


class TranslationModel(Protocol):
    """Injected model client. Tests use fakes — never a live API (CLAUDE.md)."""

    def complete(self, prompt: str) -> TranslationResult: ...


class PromptTranslation(BaseModel):
    model_config = ConfigDict(frozen=True)

    cluster_id: str
    target_model: str
    translated_text: str | None
    diff: str
    rationale: tuple[str, ...]
    applied: bool = False  # drafts only; this module cannot apply
    error: str | None = None


def _hint_for(target_model: str) -> str:
    lowered = target_model.lower()
    for prefix, hint in TARGET_HINTS.items():
        if prefix in lowered:
            return hint
    return _DEFAULT_HINT


def _instruction(
    source_prompt: str,
    target_model: str,
    contract: OutputContract | None,
    policy: ToolPolicy | None,
) -> str:
    lines = [
        f"Rewrite this system prompt for the model `{target_model}`.",
        _hint_for(target_model),
        "HARD REQUIREMENTS — the rewritten prompt must preserve:",
    ]
    if contract is not None:
        lines.append(
            f"- output contract: dominant type `{contract.dominant_type}`, "
            f"json_valid_rate {contract.json_valid_rate:.2f}, "
            f"length p50 ~{contract.length.p50} chars"
        )
    if policy is not None and policy.constraints:
        ordered = ", ".join(f"{c.before} before {c.after}" for c in policy.constraints[:5])
        lines.append(f"- tool ordering: {ordered}")
    lines += [
        'Reply as JSON: {"translated": "<prompt>", "rationale": ["<one line per change>"]}.',
        "--- SOURCE PROMPT ---",
        source_prompt,
    ]
    return "\n".join(lines)


def _diff(source: str, translated: str, target_model: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            source.splitlines(),
            translated.splitlines(),
            fromfile="source",
            tofile=target_model,
            lineterm="",
        )
    )


def translate_prompts(
    source_prompts: Mapping[str, str],  # cluster_id -> in-tenant system prompt text
    target_model: str,
    model: TranslationModel,
    budget: SpendBudget,
    *,
    contracts: Mapping[str, OutputContract] | None = None,
    policies: Mapping[str, ToolPolicy] | None = None,
    estimated_cost_per_call: Decimal = Decimal("0.02"),
) -> tuple[PromptTranslation, ...]:
    translations: list[PromptTranslation] = []
    for cluster_id in sorted(source_prompts):
        source = source_prompts[cluster_id]
        if not budget.can_spend(estimated_cost_per_call):
            translations.append(
                PromptTranslation(
                    cluster_id=cluster_id,
                    target_model=target_model,
                    translated_text=None,
                    diff="",
                    rationale=(),
                    error="budget exhausted before this cluster",
                )
            )
            continue
        result = model.complete(
            _instruction(
                source,
                target_model,
                (contracts or {}).get(cluster_id),
                (policies or {}).get(cluster_id),
            )
        )
        budget.charge(result.cost_usd)
        try:
            payload = json.loads(result.text)
            translated = str(payload["translated"])
            rationale = tuple(str(r) for r in payload.get("rationale", []))
        except (ValueError, KeyError, TypeError):
            translations.append(
                PromptTranslation(
                    cluster_id=cluster_id,
                    target_model=target_model,
                    translated_text=None,
                    diff="",
                    rationale=(),
                    error="model response was not valid translation JSON",
                )
            )
            continue
        translations.append(
            PromptTranslation(
                cluster_id=cluster_id,
                target_model=target_model,
                translated_text=translated,
                diff=_diff(source, translated, target_model),
                rationale=rationale,
            )
        )
    return tuple(translations)
