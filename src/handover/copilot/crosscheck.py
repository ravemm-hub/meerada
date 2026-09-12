"""Cross-Check — the model that examines models.

Same task, several models; then every answer is examined by a jury drawn
from the *other* labs (never its own family), on the dimension the task calls
for. The report says what each model got right, where the jurors flagged
trouble, how much the jurors agreed, and which answer wins — a neutral
cross-reference no single vendor can give you.

Pure orchestration: callers are injected (the user's own keys), the jury is
:mod:`handover.verify.jury`, and the cost of every juror call is reported.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from handover.replay.budget import DailyBudget
from handover.replay.openai_client import ChatCaller
from handover.schema.verdict import Dimension, JudgeRequest, JuryResult
from handover.verify.jury import MIN_JURORS, Juror, Jury, JuryConfigError

_FENCE = re.compile(r"```")
_LABS: tuple[tuple[str, str], ...] = (
    ("claude", "anthropic"),
    ("anthropic/", "anthropic"),
    ("gpt-", "openai"),
    ("o1", "openai"),
    ("o3", "openai"),
    ("o4", "openai"),
    ("chatgpt", "openai"),
    ("openai/", "openai"),
    ("gemini", "google"),
    ("gemma", "google"),
    ("google/", "google"),
    ("llama", "meta"),
    ("muse", "meta"),
    ("meta", "meta"),
    ("deepseek", "deepseek"),
    ("mistral", "mistral"),
    ("mixtral", "mistral"),
    ("codestral", "mistral"),
    ("qwen", "alibaba"),
    ("kimi", "moonshot"),
    ("moonshotai/", "moonshot"),
    ("grok", "xai"),
    ("x-ai/", "xai"),
    ("glm", "zai"),
    ("z-ai/", "zai"),
    ("minimax", "minimax"),
    ("phi-", "microsoft"),
    ("microsoft/", "microsoft"),
    ("command", "cohere"),
    ("cohere/", "cohere"),
)


def lab_of(model_id: str) -> str:
    """The family a model id belongs to — the neutrality rule keys on this."""
    low = model_id.lower()
    for hint, lab in _LABS:
        if low.startswith(hint) or ("/" in low and low.split("/", 1)[1].startswith(hint)):
            return lab
    return low.split("/", 1)[0] if "/" in low else "unknown"


def dimension_for(answer: str, *, has_context: bool) -> Dimension:
    if has_context:
        return "faithfulness"
    if _FENCE.search(answer) or "def " in answer or "function " in answer:
        return "code_correctness"
    return "instruction_following"


@dataclass(frozen=True)
class Answer:
    session_id: str
    model_id: str
    text: str


@dataclass
class Examined:
    answer: Answer
    dimension: Dimension
    result: JuryResult | None  # None = no neutral panel could be seated
    jurors: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def score(self) -> float:
        return self.result.score if self.result else 0.0


@dataclass
class CrossCheckReport:
    question: str
    examined: list[Examined]
    cost_usd: Decimal
    text: str  # the human report, rendered once

    def as_dict(self) -> dict[str, Any]:
        rows = []
        for e in sorted(self.examined, key=lambda x: -x.score):
            r = e.result
            rows.append(
                {
                    "session_id": e.answer.session_id,
                    "model": e.answer.model_id,
                    "lab": lab_of(e.answer.model_id),
                    "dimension": e.dimension,
                    "jurors": e.jurors,
                    "note": e.note,
                    "score": r.score if r else None,
                    "calibrated_prob": r.calibrated_prob if r else None,
                    "agreement": r.agreement if r else None,
                    "low_agreement": r.low_agreement if r else True,
                    "status": r.verification.status if r else "unknown",
                    "flags": [s.model_dump() for s in r.flagged_spans] if r else [],
                    "reasons": [v.reason for v in r.verdicts] if r else [],
                }
            )
        return {
            "question": self.question,
            "rows": rows,
            "cost_usd": float(self.cost_usd),
            "text": self.text,
        }


class CrossCheck:
    """``caller_for`` builds a caller for any model id the user can run;
    ``candidates`` are the model ids available as jurors (cheapest first)."""

    def __init__(
        self,
        caller_for: Callable[[str], ChatCaller],
        candidates: Sequence[str],
        budget: DailyBudget,
        *,
        store: Callable[[JudgeRequest, JuryResult], object] | None = None,
        jurors_per_answer: int = MIN_JURORS,
    ) -> None:
        self._caller_for = caller_for
        self._candidates = list(candidates)
        self._budget = budget
        self._store = store
        self._k = jurors_per_answer

    def panel_for(self, answer_model: str, *, exclude: Sequence[str] = ()) -> list[Juror]:
        """Up to k jurors, one per lab, never the answer's family."""
        kin = lab_of(answer_model)
        seen: set[str] = set()
        panel: list[Juror] = []
        for mid in self._candidates:
            lab = lab_of(mid)
            if (
                mid == answer_model
                or mid in exclude
                or lab == kin
                or lab in seen
                or lab == "unknown"
            ):
                continue
            seen.add(lab)
            panel.append(Juror(mid, lab, self._caller_for(mid)))
            if len(panel) == self._k:
                break
        return panel

    def examine(
        self, question: str, answers: Sequence[Answer], *, context: str | None = None
    ) -> CrossCheckReport:
        examined: list[Examined] = []
        total = Decimal("0")
        for a in answers:
            dim = dimension_for(a.text, has_context=bool(context))
            panel = self.panel_for(a.model_id)
            ex = Examined(a, dim, None, [j.model_id for j in panel])
            if len(panel) < MIN_JURORS:
                ex.note = (
                    f"needs {MIN_JURORS} other labs to seat a neutral panel (have {len(panel)}) — "
                    "connect a key from another lab (an OpenRouter key covers them all)"
                )
                examined.append(ex)
                continue
            try:
                jury = Jury(panel, self._budget, store=self._store)
            except JuryConfigError as exc:
                ex.note = str(exc)
                examined.append(ex)
                continue
            req = JudgeRequest(
                action="judge",
                dimension=dim,
                prompt=question,
                answer=a.text,
                context=context,
                answer_family=lab_of(a.model_id),
            )
            ex.result = jury.judge(req)
            total += ex.result.cost_usd
            if ex.result.budget_stopped:
                ex.note = "jury budget for today is spent"
            examined.append(ex)
        return CrossCheckReport(question, examined, total, render(question, examined, total))


def _bar(x: float, width: int = 10) -> str:
    n = round(x * width)
    return "█" * n + "░" * (width - n)


def render(question: str, examined: Sequence[Examined], cost: Decimal) -> str:
    """The report a person reads — ranked, with the jurors' own words."""
    lines = ["🔎 CROSS-CHECK — every answer examined by a jury from the other labs", ""]
    ranked = sorted(examined, key=lambda e: -e.score)
    for n, e in enumerate(ranked, 1):
        r = e.result
        head = f"{n}. {e.answer.model_id} ({lab_of(e.answer.model_id)}) · {e.dimension}"
        if r is None:
            lines.append(f"{head}\n   ⚠ not examined — {e.note}")
            continue
        verdict = {
            "pass": "✅ holds up",
            "fail": "❌ does not hold up",
            "unknown": "❔ jury split",
        }[r.verification.status]
        lines.append(
            f"{head}\n   {_bar(r.score)} {r.score:.2f} · {verdict} · "
            f"jurors agree {int(r.agreement * 100)}%"
            f" · confidence {r.calibrated_prob:.2f} · jurors: {', '.join(e.jurors)}"
        )
        for v in r.verdicts:
            lines.append(f"   - {v.judge_id}: {v.reason}")
        flagged = sorted({s.reason for s in r.flagged_spans if s.reason})
        if flagged:
            lines.append("   ⚑ flagged: " + " | ".join(flagged[:5]))
        if e.note:
            lines.append(f"   ⚠ {e.note}")
        lines.append("")
    judged = [e for e in ranked if e.result is not None and not e.result.low_agreement]
    if judged:
        best = judged[0]
        lines.append(
            f"WINNER: {best.answer.model_id} — score {best.score:.2f} with a panel that agreed."
        )
    else:
        lines.append(
            "NO WINNER: no answer got a neutral panel that agreed. "
            "Add keys from more labs or re-ask."
        )
    lines.append(
        f"Jury cost: ${cost:.4f} · every juror is from a lab other than the answer it judged."
    )
    return "\n".join(lines)
