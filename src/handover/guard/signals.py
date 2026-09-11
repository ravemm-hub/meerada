"""Stall / burn detection — is the model still moving, or burning money in place?

Pure: feed :class:`Event` objects (one per model turn or tool call), get a
:class:`Verdict`. No clocks, no I/O; the caller supplies timestamps, so the
watcher and the tests drive it the same way.

The core distinction the user asked for — **stuck vs. working hard** — is made
by *progress*: signals of cost and time with progress markers present (files
written, tests passing, new information per step) read as "working hard,
watch the budget"; the same signals with no progress read as "stalled".
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from handover.guard.policy import Policy

State = Literal["ok", "watch", "stalled", "burning"]
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class Event:
    ts: float  # seconds (any monotonic or epoch base, consistently)
    kind: str  # assistant | tool | user | progress
    out_tokens: int = 0
    in_tokens: int = 0
    thinking_tokens: int = 0
    cost_usd: float = 0.0
    text: str = ""  # assistant text (for repetition)
    tool: str = ""  # tool name for tool calls
    tool_args: str = ""  # canonical args string for loop detection
    progress: bool = False  # a verifiable step forward (file changed, test passed, ...)


@dataclass(frozen=True)
class Baseline:
    """What the exchange says this kind of task should cost / take (p90)."""

    cost_usd: float | None = None
    seconds: float | None = None


@dataclass
class Verdict:
    state: State = "ok"
    score: int = 0  # 0..100, how sure we are it's stuck/burning
    reasons: list[str] = field(default_factory=list)
    spent_usd: float = 0.0
    elapsed_s: float = 0.0
    since_progress_s: float = 0.0
    out_tokens: int = 0
    thinking_tokens: int = 0
    tool_loops: int = 0
    repeat_ratio: float = 0.0
    working_hard: bool = False  # costly/slow but visibly progressing

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "score": self.score,
            "reasons": list(self.reasons),
            "spent_usd": round(self.spent_usd, 4),
            "elapsed_s": round(self.elapsed_s, 1),
            "since_progress_s": round(self.since_progress_s, 1),
            "out_tokens": self.out_tokens,
            "thinking_tokens": self.thinking_tokens,
            "tool_loops": self.tool_loops,
            "repeat_ratio": round(self.repeat_ratio, 2),
            "working_hard": self.working_hard,
        }


def trigram_overlap(a: str, b: str) -> float:
    """Share of ``b``'s word trigrams already present in ``a`` (0..1)."""
    wa, wb = _WORD.findall(a.lower()), _WORD.findall(b.lower())
    ta = {tuple(wa[i : i + 3]) for i in range(len(wa) - 2)}
    tb = [tuple(wb[i : i + 3]) for i in range(len(wb) - 2)]
    if not tb or not ta:
        return 0.0
    return sum(1 for t in tb if t in ta) / len(tb)


class StallDetector:
    """One per task/session. ``observe`` returns the verdict *as of that event*;
    ``check(now)`` re-evaluates silence without a new event."""

    def __init__(
        self, policy: Policy, baseline: Baseline | None = None, *, window: int = 24
    ) -> None:
        self._p = policy
        self._base = baseline or Baseline()
        self._events: deque[Event] = deque(maxlen=window)
        self._texts: deque[str] = deque(maxlen=6)
        self.started: float | None = None
        self.last_ts: float | None = None
        self.last_progress: float | None = None
        self.spent = 0.0
        self.out_tokens = 0
        self.thinking = 0
        self.verdict = Verdict()

    # ------------------------------------------------------------------ feed --
    def observe(self, ev: Event) -> Verdict:
        if self.started is None:
            self.started = ev.ts
        self.last_ts = ev.ts
        self.spent += ev.cost_usd
        self.out_tokens += ev.out_tokens
        self.thinking += ev.thinking_tokens
        if ev.progress:
            self.last_progress = ev.ts  # only the MODEL's verifiable steps count as progress
        if ev.kind == "user":  # a human spoke: a new task starts, old loops don't count
            self.started = ev.ts
            self.last_progress = None
            self._events.clear()
            self._texts.clear()
        self._events.append(ev)
        if ev.kind == "assistant" and ev.text.strip():
            self._texts.append(ev.text)
        return self.check(ev.ts)

    # ---------------------------------------------------------------- judge --
    def _tool_loops(self) -> int:
        """The most-repeated identical tool call since the last verifiable progress.
        Interleaved text turns don't break a loop; a real step forward does."""
        since = self.last_progress if self.last_progress is not None else (self.started or 0.0)
        counts: dict[tuple[str, str], int] = {}
        for e in self._events:
            if e.kind == "tool" and not e.progress and e.ts >= since:
                key = (e.tool, e.tool_args)
                counts[key] = counts.get(key, 0) + 1
        return max(counts.values(), default=0)

    def _repeat_ratio(self) -> float:
        if len(self._texts) < 2:
            return 0.0
        prev = " ".join(list(self._texts)[:-1])
        return trigram_overlap(prev, self._texts[-1])

    def check(self, now: float) -> Verdict:
        p = self._p
        v = Verdict(spent_usd=self.spent, out_tokens=self.out_tokens, thinking_tokens=self.thinking)
        if self.started is None or self.last_ts is None:
            self.verdict = v
            return v
        v.elapsed_s = max(0.0, now - self.started)
        anchor = self.last_progress if self.last_progress is not None else self.started
        v.since_progress_s = max(0.0, now - anchor)
        v.tool_loops = self._tool_loops()
        v.repeat_ratio = self._repeat_ratio()
        recent_progress = self.last_progress is not None and v.since_progress_s < p.silence_s
        stuck, burn = 0, 0

        if now - self.last_ts >= p.silence_s and not recent_progress:
            stuck += 40
            v.reasons.append(f"silent for {int(now - self.last_ts)}s")
        if v.tool_loops >= p.max_repeat:
            stuck += 45
            v.reasons.append(f"same tool call {v.tool_loops}x in a row")
        if v.repeat_ratio >= p.repeat_ratio and len(self._texts) >= 2:
            stuck += 40
            v.reasons.append(f"repeating itself ({int(v.repeat_ratio * 100)}% overlap)")
        if self.out_tokens and self.thinking / max(1, self.out_tokens) > p.max_thinking_ratio:
            burn += 25
            v.reasons.append("thinking far more than it says")
        cap = p.cap_hit(self.spent, self.spent)
        if cap:
            burn += 60
            v.reasons.append(f"{cap} reached (${self.spent:.2f})")
        if self._base.cost_usd and self.spent > p.burn_multiplier * self._base.cost_usd:
            burn += 40
            v.reasons.append(
                f"${self.spent:.2f} spent vs ~${self._base.cost_usd:.2f} expected "
                "for this kind of task"
            )
        if self._base.seconds and v.elapsed_s > p.burn_multiplier * self._base.seconds:
            burn += 20
            v.reasons.append(f"{int(v.elapsed_s)}s vs ~{int(self._base.seconds)}s expected")

        if recent_progress and (stuck or burn):
            v.working_hard = True
            v.reasons.append("but it is still making verifiable progress")
        score = max(stuck, burn) if not recent_progress else min(burn, 55)
        if cap:
            score = max(score, 90)
        v.score = min(100, score)
        if cap or (burn >= 60 and not recent_progress):
            v.state = "burning"
        elif stuck >= 40 and not recent_progress:
            v.state = "stalled"
        elif v.score >= 25:
            v.state = "watch"
        self.verdict = v
        return v
