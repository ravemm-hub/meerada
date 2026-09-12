"""The jury — grade-C verification by a panel of foreign models (SPEC §5.2).

Rules, enforced here and tested:

* three jurors from three different labs;
* a juror never judges an answer from its own family;
* every pairwise comparison runs twice in reversed order (position bias);
* the rubric deducts for padding (length bias);
* Fleiss' kappa is always reported; kappa < 0.4 -> ``low_agreement`` and the
  verification is ``unknown`` — it enters no public score;
* a hard daily budget: exceeding stops the panel, never warns.

Every verdict is handed to an optional store — the future training set for our
own judge (stage 4). Content stays in-tenant; the store exports metadata only.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from handover.copilot.pricing import price_for
from handover.replay.budget import DailyBudget
from handover.replay.openai_client import ChatCaller
from handover.schema.trace import Verification
from handover.schema.verdict import (
    FlaggedSpan,
    JudgeRequest,
    JudgeVerdict,
    JuryResult,
    category,
)
from handover.verify.rubrics import parse_verdict, system_prompt, user_prompt

KAPPA_FLOOR = 0.4
MIN_JURORS = 3


@dataclass(frozen=True)
class Juror:
    model_id: str
    lab: str  # openai | anthropic | google | meta | deepseek | mistral | ...
    caller: ChatCaller


class JuryConfigError(ValueError):
    pass


def fleiss_kappa(matrix: Sequence[Sequence[int]]) -> float | None:
    """Fleiss' kappa. ``matrix[i][j]`` = number of raters who put subject i in
    category j; every row must sum to the same n >= 2. None when undefined."""
    rows = [list(r) for r in matrix if sum(r) >= 2]
    if len(rows) < 2:
        return None
    n = sum(rows[0])
    n_subj, n_cat = len(rows), len(rows[0])
    if any(sum(r) != n or len(r) != n_cat for r in rows):
        return None
    p_j = [sum(r[j] for r in rows) / (n_subj * n) for j in range(n_cat)]
    p_i = [(sum(c * c for c in r) - n) / (n * (n - 1)) for r in rows]
    p_bar = sum(p_i) / n_subj
    p_e = sum(p * p for p in p_j)
    if p_e >= 1.0:
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def _agreement(scores: Sequence[float]) -> float:
    if not scores:
        return 0.0
    cats = [category(s) for s in scores]
    return max(cats.count(c) for c in set(cats)) / len(cats)


class Jury:
    def __init__(
        self,
        jurors: Sequence[Juror],
        budget: DailyBudget,
        *,
        est_cost_per_call: Decimal = Decimal("0.005"),
        max_tokens: int = 600,
        store: Callable[[JudgeRequest, JuryResult], object] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        labs = {j.lab for j in jurors}
        if len(jurors) < MIN_JURORS or len(labs) < MIN_JURORS:
            raise JuryConfigError(f"a jury needs {MIN_JURORS} jurors from {MIN_JURORS} labs")
        self._jurors = list(jurors)
        self._budget = budget
        self._est = est_cost_per_call
        self._max_tokens = max_tokens
        self._store = store
        self._clock = clock

    # --------------------------------------------------------------- panel --
    def panel_for(self, req: JudgeRequest) -> list[Juror]:
        """Jurors allowed to judge this request: never the answer's own family."""
        kin = {f for f in (req.answer_family, req.answer_b_family) if f}
        return [j for j in self._jurors if j.lab not in kin]

    def _ask(self, juror: Juror, req: JudgeRequest, *, swap: bool) -> JudgeVerdict | None:
        if not self._budget.can_spend(self._est):
            return None
        completion = juror.caller.complete(
            juror.model_id,
            system_prompt(req.dimension),
            [{"role": "user", "content": user_prompt(req, swap=swap)}],
            self._max_tokens,
        )
        pin, pout = price_for(juror.model_id)
        cost = (
            Decimal(completion.input_tokens) * pin + Decimal(completion.output_tokens) * pout
        ) / Decimal(1_000_000)
        self._budget.record(cost)
        score, prob, spans, reason = parse_verdict(completion.text, len(req.answer))
        if swap:
            score = 1.0 - score  # the juror saw B first: its "A better" is our "B better"
            spans = ()
        return JudgeVerdict(
            score=score,
            calibrated_prob=prob,
            flagged_spans=spans,
            dimension=req.dimension,
            reason=reason or "no reason given",
            judge_id=juror.model_id,
            judge_lab=juror.lab,
            position=("ba" if swap else "ab") if req.action == "compare" else "",
            cost_usd=cost,
        )

    # -------------------------------------------------------------- verdict --
    def judge(self, req: JudgeRequest, *, kappa: float | None = None) -> JuryResult:
        panel = self.panel_for(req)
        verdicts: list[JudgeVerdict] = []
        stopped = False
        for juror in panel:
            orders = (False, True) if req.action == "compare" else (False,)
            for swap in orders:
                v = self._ask(juror, req, swap=swap)
                if v is None:
                    stopped = True
                    break
                verdicts.append(v)
            if stopped:
                break
        return self._combine(req, verdicts, kappa=kappa, stopped=stopped, panel_size=len(panel))

    def judge_many(self, reqs: Sequence[JudgeRequest]) -> list[JuryResult]:
        """A batch: Fleiss' kappa is computed across it and stamped on every result."""
        first = [self.judge(r) for r in reqs]
        matrix = [_row(r) for r in first if r.n_judges >= 2]
        k = fleiss_kappa(matrix)
        return [
            self._combine(
                req,
                list(res.verdicts),
                kappa=k,
                stopped=res.budget_stopped,
                panel_size=res.n_judges,
            )
            for req, res in zip(reqs, first, strict=True)
        ]

    def _combine(
        self,
        req: JudgeRequest,
        verdicts: list[JudgeVerdict],
        *,
        kappa: float | None,
        stopped: bool,
        panel_size: int,
    ) -> JuryResult:
        per_judge = _per_judge(verdicts)
        scores = list(per_judge.values())
        n = len(per_judge)
        agreement = _agreement(scores)
        low = n < MIN_JURORS or (kappa is not None and kappa < KAPPA_FLOOR) or agreement < 0.6
        mean = sum(scores) / n if n else 0.5
        prob = sum(v.calibrated_prob for v in verdicts) / len(verdicts) if verdicts else 0.0
        spans: tuple[FlaggedSpan, ...] = tuple(s for v in verdicts for s in v.flagged_spans)
        signal = f"jury_{req.dimension}"
        if low:
            verification = Verification(
                status="unknown",
                method="judge",
                signal=signal,
                confidence=0.0,
                evidence_grade="declared",
            )
        else:
            passed = mean >= 0.7
            verification = Verification(
                status="pass" if passed else "fail",
                method="judge",
                signal=signal,
                confidence=round(min(1.0, prob * agreement), 4),
                evidence_grade="derived",
            )
        result = JuryResult(
            action=req.action,
            dimension=req.dimension,
            verdicts=tuple(verdicts),
            score=round(mean, 4),
            calibrated_prob=round(prob, 4),
            agreement=round(agreement, 4),
            kappa=kappa,
            low_agreement=low,
            n_judges=n,
            flagged_spans=spans,
            verification=verification,
            cost_usd=sum((v.cost_usd for v in verdicts), Decimal("0")),
            budget_stopped=stopped,
        )
        if self._store is not None and verdicts:
            self._store(req, result)
        return result


def _per_judge(verdicts: Sequence[JudgeVerdict]) -> dict[str, float]:
    """One score per juror: a compare's two orders average into one."""
    acc: dict[str, list[float]] = {}
    for v in verdicts:
        acc.setdefault(v.judge_id, []).append(v.score)
    return {k: sum(vs) / len(vs) for k, vs in acc.items()}


def _row(res: JuryResult) -> list[int]:
    row = [0, 0, 0]
    for s in _per_judge(res.verdicts).values():
        row[category(s)] += 1
    return row
