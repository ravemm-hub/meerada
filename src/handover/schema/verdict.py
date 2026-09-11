"""The judge's verdict — the one frozen shape every judge (a jury of foreign
models today, our own trained judge tomorrow) must speak (SPEC §5.2).

A verdict is *derived* evidence (grade C): it never outranks a programmatic
check, and a low-agreement jury yields ``unknown`` — excluded from every public
number. The shape is deliberately small so verdicts can be stored, exported as
metadata, and used as training targets without change.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from handover.schema.trace import StrictModel, Verification

Dimension = Literal[
    "faithfulness",  # answer vs. the supplied context/sources (RAG)
    "factuality",  # answer vs. the world (needs knowledge; start with faithfulness)
    "instruction_following",  # did it do what was asked, in the asked form
    "code_correctness",  # code that would work (programmatic checks win when present)
    "pairwise_preference",  # A vs. B on the same task
]
Action = Literal["judge", "compare", "hallucinations"]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]


class FlaggedSpan(StrictModel):
    """A slice of the answer the judge objects to (character offsets)."""

    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    reason: Annotated[str, Field(max_length=200)]


class JudgeRequest(StrictModel):
    action: Action
    dimension: Dimension
    prompt: str
    answer: str
    answer_b: str | None = None  # compare: the other side
    context: str | None = None  # faithfulness / hallucinations: the sources
    expected_output: str | None = None  # a known-good answer, when there is one
    answer_family: str = ""  # lab of the model that wrote ``answer`` (never judged by kin)
    answer_b_family: str = ""


class JudgeVerdict(StrictModel):
    """One judge, one request."""

    score: Unit  # 0 = wrong/unfaithful, 1 = fully right; compare: P(A better than B)
    calibrated_prob: Unit  # the judge's own confidence that ``score`` is right
    flagged_spans: tuple[FlaggedSpan, ...] = ()
    dimension: Dimension
    reason: Annotated[str, Field(max_length=300)]  # one line
    judge_id: str  # model id of the judge
    judge_lab: str  # its family — the neutrality rule is enforced on this
    judge_grade: Literal["measured", "derived", "declared"] = "derived"
    position: Literal["", "ab", "ba"] = ""  # compare: which order this judge saw
    cost_usd: Decimal = Decimal("0")


class JuryResult(StrictModel):
    """The panel's combined answer. ``verification`` is what the rest of the
    system consumes; the rest is the evidence behind it."""

    action: Action
    dimension: Dimension
    verdicts: tuple[JudgeVerdict, ...]
    score: Unit  # mean judge score
    calibrated_prob: Unit  # mean confidence
    agreement: Unit  # share of judges in the majority category
    kappa: float | None  # Fleiss' kappa across the batch this item ran in (None = single item)
    low_agreement: bool
    n_judges: Annotated[int, Field(ge=0)]
    flagged_spans: tuple[FlaggedSpan, ...] = ()
    verification: Verification
    cost_usd: Decimal
    budget_stopped: bool = False


def category(score: float) -> int:
    """Three rater categories for agreement statistics: fail / unsure / pass."""
    if score < 0.4:
        return 0
    if score < 0.7:
        return 1
    return 2
