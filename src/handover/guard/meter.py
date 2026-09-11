"""The guard inside LLManager: every model call passes through a
:class:`GuardedCaller`, which meters it (tokens, cost, time), runs the cage on
what is about to leave the machine, and refuses the next call once a budget is
hit and the policy says ``stop``. :class:`GuardHub` owns the policy, one stall
detector per session, the day's spend and the alert sinks.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from handover.guard.alerts import Alert, MultiSink, RingSink
from handover.guard.cage import Finding, decision, inspect_outbound
from handover.guard.policy import Policy
from handover.guard.signals import Baseline, Event, StallDetector, Verdict
from handover.replay.openai_client import ChatCaller, ChatCompletion


class GuardBlocked(RuntimeError):
    """Raised instead of calling the model; the message is user-facing."""


class GuardHub:
    def __init__(
        self,
        policy: Policy,
        sink: MultiSink | None = None,
        ring: RingSink | None = None,
        *,
        clock: Callable[[], float] = time.time,
        baseline_for: Callable[[str], Baseline] | None = None,
    ) -> None:
        self.policy = policy
        self.ring = ring or RingSink()
        self._sink = sink or MultiSink(self.ring)
        self._clock = clock
        self._baseline_for = baseline_for or (lambda _m: Baseline())
        self.detectors: dict[str, StallDetector] = {}
        self.models: dict[str, str] = {}
        self._last_state: dict[str, str] = {}
        self.spent_day = 0.0
        self._day = ""

    # ----------------------------------------------------------- bookkeeping --
    def _roll_day(self) -> None:
        day = time.strftime("%Y-%m-%d", time.gmtime(self._clock()))
        if day != self._day:
            self._day, self.spent_day = day, 0.0

    def detector(self, sid: str, model: str) -> StallDetector:
        d = self.detectors.get(sid)
        if d is None or self.models.get(sid) != model:
            d = StallDetector(self.policy, self._baseline_for(model))
            if sid in self.detectors:  # a handshake keeps the spend, restarts the clock
                d.spent = self.detectors[sid].spent
            self.detectors[sid] = d
            self.models[sid] = model
        return d

    def alert(self, level: str, title: str, body: str, sid: str = "") -> None:
        self._sink.send(Alert(level, title, body, session=sid, ts=self._clock()))

    def _announce(self, sid: str, v: Verdict) -> None:
        """Alert on state changes only — never spam the same verdict."""
        if v.state == self._last_state.get(sid, "ok"):
            return
        self._last_state[sid] = v.state
        if v.state in ("stalled", "burning"):
            title = "task looks stuck" if v.state == "stalled" else "task is burning money"
            self.alert(v.state, title, "; ".join(v.reasons) + f" · ${v.spent_usd:.2f} so far", sid)
        elif v.state == "watch" and v.working_hard:
            self.alert("warn", "working hard — watch the budget", "; ".join(v.reasons), sid)

    # ---------------------------------------------------------------- calls --
    def before_call(self, sid: str, model: str, outbound: str) -> list[Finding]:
        """Cage + budget gate. Raises :class:`GuardBlocked` when the call must not go."""
        self._roll_day()
        if not self.policy.enabled:
            return []
        d = self.detector(sid, model)
        cap = self.policy.cap_hit(d.spent, self.spent_day)
        if cap and self.policy.action == "stop":
            self.alert(
                "burning", "call refused", f"{cap} reached — raise it in the guard policy", sid
            )
            raise GuardBlocked(
                f"🛡 Guard stopped this call: {cap} reached (${d.spent:.2f}). "
                "Raise the cap in ~/.meerada/guard.toml."
            )
        findings = inspect_outbound(outbound, self.policy)
        if findings:
            what = "; ".join(f"{f.what} ({f.snippet})" for f in findings[:4])
            if decision(findings) == "block":
                self.alert("blocked", "blocked before it left the machine", what, sid)
                raise GuardBlocked(
                    f"🛡 Guard blocked this call — {what}. Remove it from the message or "
                    "attachment, or allow it in the guard policy."
                )
            self.alert("warn", "leaving the workspace", what, sid)
        return findings

    def after_call(
        self,
        sid: str,
        model: str,
        completion: ChatCompletion,
        cost_usd: float,
        seconds: float,
        *,
        text: str = "",
    ) -> Verdict:
        d = self.detector(sid, model)
        self.spent_day += cost_usd
        now = self._clock()
        d.observe(Event(ts=now - seconds, kind="user"))  # the request went out then
        v = d.observe(
            Event(
                ts=now,
                kind="assistant",
                out_tokens=completion.output_tokens,
                in_tokens=completion.input_tokens,
                cost_usd=cost_usd,
                text=text or completion.text,
            )
        )
        self._announce(sid, v)
        return v

    def snapshot(self) -> dict[str, Any]:
        self._roll_day()
        sessions = {}
        now = self._clock()
        for sid, d in self.detectors.items():
            v = d.check(now)
            self._announce(sid, v)
            sessions[sid] = {"model": self.models.get(sid, ""), **v.as_dict()}
        worst = "ok"
        for row in sessions.values():
            st = str(row["state"])
            if (
                st == "burning"
                or (st == "stalled" and worst != "burning")
                or (st == "watch" and worst == "ok")
            ):
                worst = st
        return {
            "enabled": self.policy.enabled,
            "policy_source": self.policy.source,
            "state": worst,
            "spent_today": round(self.spent_day, 4),
            "sessions": sessions,
            "alerts": self.ring.recent(30),
        }


class GuardedCaller:
    """Wraps any :class:`ChatCaller`; identical interface, guarded."""

    def __init__(
        self, inner: ChatCaller, hub: GuardHub, sid: str, price_in: float, price_out: float
    ) -> None:
        self._inner, self._hub, self._sid = inner, hub, sid
        self._pin, self._pout = price_in, price_out

    def complete(
        self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int
    ) -> ChatCompletion:
        last = messages[-1]["content"] if messages else ""
        self._hub.before_call(self._sid, model, f"{system}\n{last}")
        t0 = time.monotonic()
        completion = self._inner.complete(model, system, messages, max_tokens)
        seconds = time.monotonic() - t0
        cost = (
            completion.input_tokens * self._pin + completion.output_tokens * self._pout
        ) / 1_000_000
        self._hub.after_call(self._sid, model, completion, cost, seconds)
        return completion
