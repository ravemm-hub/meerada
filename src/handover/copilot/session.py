"""Copilot sessions — one cockpit that drives many models, in parallel.

A ``Session`` wraps a single model behind the same ``ChatCaller`` seam the replay
engine uses, keeping message history and a running token/cost tally. A
``SessionManager`` fans one plain-language intent out to several models at once
(shared context, one optimize pass per model), so the user manages many model
conversations from one place instead of juggling tabs. The network seam is
injected — tests use fakes and never call a live API (CLAUDE.md).
"""

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from handover.copilot.optimize import OptimizedPrompt, optimize
from handover.replay.openai_client import ChatCaller

# model_id -> caller that routes to that model's provider.
CallerFactory = Callable[[str], ChatCaller]
_ZERO = Decimal("0")


_HTTP_HINTS: dict[str, str] = {
    "401": "key rejected by the provider — reconnect it under Keys",
    "402": "no credit left on your account at this provider",
    "403": "your account isn't allowed to use this model",
    "404": "model not available on your account at this provider",
    "429": "rate limit on YOUR provider account (tokens/min) — wait a minute, "
    "or continue on a cheaper model / shorter history",
    "500": "provider error — try again",
    "502": "provider error — try again",
    "503": "provider overloaded — try again in a moment",
    "529": "provider overloaded — try again in a moment",
}


def friendly_error(exc: BaseException) -> str:
    """Turn a raw HTTP/network exception into something a user can act on. The
    bill and the limits live at the provider, so we say exactly that."""
    raw = f"{type(exc).__name__}: {exc}"
    for code, hint in _HTTP_HINTS.items():
        if f"Error {code}" in raw or f" {code}:" in raw or raw.endswith(code):
            return f"{code} — {hint}"
    if "timed out" in raw or "TimeoutError" in raw:
        return "timeout — the provider took too long; try again"
    if "URLError" in raw or "getaddrinfo" in raw or "Connection" in raw:
        return "network — can't reach the provider; check your connection"
    return raw[:120]


class Turn(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    content: str


class SessionReply(BaseModel):
    """One model's answer to one intent, with the lean prompt and its cost."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    prompt: OptimizedPrompt
    error: str | None = None


class Session:
    """A single-model conversation with local history and a cost tally."""

    def __init__(
        self,
        model_id: str,
        caller: ChatCaller,
        *,
        price_in_per_mtok: Decimal = _ZERO,
        price_out_per_mtok: Decimal = _ZERO,
        max_tokens: int = 512,
        shared_context: str = "",
    ) -> None:
        self.model_id = model_id
        self._caller = caller
        self._price_in = price_in_per_mtok
        self._price_out = price_out_per_mtok
        self._max_tokens = max_tokens
        self._shared = shared_context.strip()
        self.history: list[Turn] = []
        self.total_tokens = 0
        self.total_cost = _ZERO
        # Handshake metadata: where this conversation came from, and the files
        # the user attached (sent as system context, so they persist across turns
        # and travel with the history when the session moves to another model).
        self.title = ""
        self.source = ""
        self.attachments: list[dict[str, str]] = []

    def seed(self, turns: list[dict[str, str]]) -> None:
        """Start from an existing conversation (import / handoff from another model)."""
        self.history = [Turn(role=t["role"], content=t["content"]) for t in turns]

    def attach(self, files: list[dict[str, str]]) -> None:
        names = {f["name"] for f in files}
        self.attachments = [a for a in self.attachments if a["name"] not in names] + list(files)

    def carry_from(self, other: "Session") -> None:
        """Take another session's whole context — history, attachments, title."""
        self.history = list(other.history)
        self.attachments = list(other.attachments)
        self.title, self.source = other.title, other.source

    def system_context(self) -> str:
        from handover.copilot.importers import context_block

        return context_block(self.attachments)

    def ask(self, intent: str) -> SessionReply:
        """Optimize ``intent`` for this model, send it, and record the exchange."""
        prompt = optimize(intent, self.model_id)
        user = f"{self._shared}\n\n{prompt.user}".strip() if self._shared else prompt.user
        messages: list[dict[str, str]] = [
            {"role": t.role, "content": t.content} for t in self.history
        ]
        messages.append({"role": "user", "content": user})
        system = prompt.system
        ctx = self.system_context()
        if ctx:
            system = f"{system}\n\n{ctx}" if system else ctx
        try:
            completion = self._caller.complete(self.model_id, system, messages, self._max_tokens)
        except Exception as exc:  # a dead session must never kill the fan-out
            return SessionReply(
                model_id=self.model_id,
                text="",
                input_tokens=0,
                output_tokens=0,
                cost_usd=_ZERO,
                prompt=prompt,
                error=friendly_error(exc),
            )
        cost = (
            Decimal(completion.input_tokens) * self._price_in
            + Decimal(completion.output_tokens) * self._price_out
        ) / Decimal(1_000_000)
        self.history.append(Turn(role="user", content=user))
        self.history.append(Turn(role="assistant", content=completion.text))
        self.total_tokens += completion.input_tokens + completion.output_tokens
        self.total_cost += cost
        return SessionReply(
            model_id=self.model_id,
            text=completion.text,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            cost_usd=cost,
            prompt=prompt,
        )


class SessionManager:
    """Open and manage many model sessions; fan one intent out to all at once."""

    def __init__(
        self,
        caller_for: CallerFactory,
        prices: Mapping[str, tuple[Decimal, Decimal]] | None = None,
        *,
        max_tokens: int = 512,
        shared_context: str = "",
    ) -> None:
        self._caller_for = caller_for
        self._prices = dict(prices or {})
        self._max_tokens = max_tokens
        self._shared = shared_context
        self.sessions: dict[str, Session] = {}

    def open(self, model_id: str) -> Session:
        if model_id not in self.sessions:
            price_in, price_out = self._prices.get(model_id, (_ZERO, _ZERO))
            self.sessions[model_id] = Session(
                model_id,
                self._caller_for(model_id),
                price_in_per_mtok=price_in,
                price_out_per_mtok=price_out,
                max_tokens=self._max_tokens,
                shared_context=self._shared,
            )
        return self.sessions[model_id]

    def fan_out(self, intent: str, models: list[str]) -> list[SessionReply]:
        """Ask every model the same intent in parallel; replies keep input order."""
        for model_id in models:
            self.open(model_id)
        if not models:
            return []
        with ThreadPoolExecutor(max_workers=min(16, len(models))) as pool:
            futures = {m: pool.submit(self.sessions[m].ask, intent) for m in models}
            return [futures[m].result() for m in models]

    def total_cost(self) -> Decimal:
        return sum((s.total_cost for s in self.sessions.values()), _ZERO)
