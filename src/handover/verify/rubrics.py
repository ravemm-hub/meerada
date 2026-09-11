"""Rubrics for the jury — one per dimension, each with an explicit deduction for
padding (length-bias neutralisation, SPEC §5.2) and a strict JSON contract so
verdicts parse the same from every lab's model.
"""

from __future__ import annotations

import json
import re
from typing import Any

from handover.schema.verdict import Dimension, FlaggedSpan, JudgeRequest

_CONTRACT = (
    'Reply with ONE JSON object and nothing else: {"score": <0..1>, "prob": <0..1>, '
    '"spans": [{"start": <int>, "end": <int>, "reason": "<short>"}], "reason": "<one line>"}. '
    '"score" is your verdict on the dimension; "prob" is how confident you are that your '
    "score is right (0.5 = coin flip). Deduct explicitly for padding, repetition and "
    "hedging that adds length without substance: a longer answer is not a better answer."
)

_RUBRIC: dict[Dimension, str] = {
    "faithfulness": (
        "Judge FAITHFULNESS: every claim in the ANSWER must be supported by the CONTEXT. "
        "Flag each unsupported or contradicted claim as a span (offsets into the ANSWER). "
        "score 1 = fully supported; 0 = mostly invented. Knowledge outside the context "
        "does not count as support, even if true."
    ),
    "factuality": (
        "Judge FACTUALITY: are the claims in the ANSWER true in the world? Flag false or "
        "unverifiable specifics (numbers, dates, names, quotes) as spans. Lower your prob "
        "when you are not sure of a fact yourself."
    ),
    "instruction_following": (
        "Judge INSTRUCTION FOLLOWING: did the ANSWER do exactly what the PROMPT asked — "
        "content, format, constraints, length, language? Flag each violated instruction."
    ),
    "code_correctness": (
        "Judge CODE CORRECTNESS: would the code in the ANSWER run and do what the PROMPT "
        "asks, including edge cases named in the prompt? Flag bugs as spans. If tests or "
        "an expected output are given, they decide."
    ),
    "pairwise_preference": (
        "Compare ANSWER A and ANSWER B to the same PROMPT. score = probability that A is "
        "the better answer (1 = A clearly better, 0 = B clearly better, 0.5 = tie). Judge "
        "substance first; length, confidence and formatting never win on their own."
    ),
}


def system_prompt(dimension: Dimension) -> str:
    return (
        "You are one juror on an impartial panel judging an AI answer. Be strict, "
        "specific and brief. " + _RUBRIC[dimension] + " " + _CONTRACT
    )


def user_prompt(req: JudgeRequest, *, swap: bool = False) -> str:
    parts = [f"PROMPT:\n{req.prompt[:6000]}"]
    if req.context:
        parts.append(f"CONTEXT (the only admissible sources):\n{req.context[:12000]}")
    if req.expected_output:
        parts.append(f"KNOWN-GOOD OUTPUT:\n{req.expected_output[:6000]}")
    if req.action == "compare" and req.answer_b is not None:
        a, b = (req.answer_b, req.answer) if swap else (req.answer, req.answer_b)
        parts.append(f"ANSWER A:\n{a[:8000]}")
        parts.append(f"ANSWER B:\n{b[:8000]}")
    else:
        parts.append(f"ANSWER:\n{req.answer[:8000]}")
    return "\n\n".join(parts)


def _first_json(text: str) -> dict[str, Any] | None:
    s = text or ""
    start = s.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(s[start : i + 1])
                        return obj if isinstance(obj, dict) else None
                    except ValueError:
                        break
        start = s.find("{", start + 1)
    return None


def _unit(v: Any, default: float) -> float:
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        return default


def parse_verdict(text: str, answer_len: int) -> tuple[float, float, tuple[FlaggedSpan, ...], str]:
    """(score, prob, spans, reason) from a juror's reply; unparseable -> (0.5, 0.0, (), ...)
    so a broken juror counts as maximally unsure, never as a pass."""
    obj = _first_json(text)
    if obj is None:
        return 0.5, 0.0, (), "unparseable verdict"
    spans: list[FlaggedSpan] = []
    for raw in obj.get("spans") or []:
        if not isinstance(raw, dict):
            continue
        try:
            start = max(0, int(raw.get("start", 0)))
            end = min(answer_len, max(start, int(raw.get("end", start))))
        except (TypeError, ValueError):
            continue
        spans.append(FlaggedSpan(start=start, end=end, reason=str(raw.get("reason", ""))[:200]))
    reason = re.sub(r"\s+", " ", str(obj.get("reason") or "")).strip()[:300]
    return _unit(obj.get("score"), 0.5), _unit(obj.get("prob"), 0.0), tuple(spans), reason
