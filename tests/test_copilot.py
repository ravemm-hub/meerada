"""Copilot: prompt optimization, parallel sessions, routing.
All callers are FAKE — no live API (CLAUDE.md)."""

import json
from decimal import Decimal
from pathlib import Path

from handover.copilot import (
    Candidate,
    Session,
    SessionManager,
    load_candidates,
    optimize,
    pick,
)


class FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text
        self.input_tokens = 20
        self.output_tokens = 8


class FakeCaller:
    """Records calls; echoes the model id. Optionally fails for one model."""

    def __init__(self, fail_for: str | None = None) -> None:
        self.fail_for = fail_for
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    def complete(self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int):
        self.calls.append((model, system, tuple(m["content"] for m in messages)))
        if self.fail_for is not None and model == self.fail_for:
            raise RuntimeError("rate limited")
        return FakeCompletion(f"answer from {model}")


# ---- optimize -------------------------------------------------------------

def test_optimize_saves_tokens_vs_naive() -> None:
    opt = optimize("please, could you kindly summarise this for me", "claude")
    assert opt.optimized_tokens < opt.naive_tokens
    assert opt.saved_pct > 0
    assert "please" not in opt.user.lower()  # filler stripped


def test_optimize_adds_json_contract_when_asked() -> None:
    opt = optimize("extract the invoice payee and amount as json", "gpt")
    assert "ONLY valid JSON" in opt.system
    assert "concise system" in opt.convention  # gpt convention applied


def test_optimize_applies_model_convention() -> None:
    assert "role and constraints first" in optimize("do x", "claude-opus-5").convention
    assert "short declarative" in optimize("do x", "gemini-3.1-pro").convention


def test_optimize_cost_saved_is_positive() -> None:
    opt = optimize("please kindly extract the fields as json thank you", "claude")
    assert opt.cost_saved(Decimal("2")) > 0


# ---- session --------------------------------------------------------------

def test_session_records_history_and_cost() -> None:
    caller = FakeCaller()
    session = Session(
        "llama-3.1-8b-instant",
        caller,
        price_in_per_mtok=Decimal("1"),
        price_out_per_mtok=Decimal("2"),
    )
    reply = session.ask("summarise this text")
    assert reply.text == "answer from llama-3.1-8b-instant"
    assert reply.error is None
    assert len(session.history) == 2  # user + assistant
    assert session.total_tokens == 28  # 20 in + 8 out
    assert session.total_cost == (Decimal("20") * 1 + Decimal("8") * 2) / Decimal(1_000_000)


def test_session_shared_context_is_prepended_once() -> None:
    caller = FakeCaller()
    session = Session("gpt-x", caller, shared_context="CONTRACT #42")
    session.ask("draft the summary")
    _, _, contents = caller.calls[0]
    assert "CONTRACT #42" in contents[-1]


# ---- session manager (parallel) ------------------------------------------

def test_fan_out_hits_every_model_and_keeps_order() -> None:
    caller = FakeCaller()
    manager = SessionManager(lambda _mid: caller)
    replies = manager.fan_out("do the thing", ["a", "b", "c"])
    assert [r.model_id for r in replies] == ["a", "b", "c"]
    assert all(r.error is None for r in replies)
    assert {c[0] for c in caller.calls} == {"a", "b", "c"}


def test_fan_out_survives_a_dead_session() -> None:
    caller = FakeCaller(fail_for="b")
    manager = SessionManager(lambda _mid: caller)
    replies = manager.fan_out("do the thing", ["a", "b", "c"])
    by_model = {r.model_id: r for r in replies}
    assert by_model["b"].error is not None
    assert by_model["a"].error is None and by_model["c"].error is None


def test_fan_out_empty_is_noop() -> None:
    manager = SessionManager(lambda _mid: FakeCaller())
    assert manager.fan_out("x", []) == []


# ---- router ---------------------------------------------------------------

def test_pick_prefers_free_then_grade() -> None:
    cands = [
        Candidate(model_id="paid-top", provider="openai", grade=95, free=False),
        Candidate(model_id="free-mid", provider="groq", grade=80, free=True),
        Candidate(model_id="free-low", provider="groq", grade=60, free=True),
    ]
    assert pick(cands).model_id == "free-mid"  # free beats higher-grade paid
    assert pick(cands, prefer_free=False).model_id == "paid-top"


def test_pick_respects_min_grade_and_empty() -> None:
    cands = [Candidate(model_id="m", provider="groq", grade=50, free=True)]
    assert pick(cands, min_grade=90) is None
    assert pick([]) is None


def test_pricing_and_provider_routing() -> None:
    from handover.copilot.pricing import price_for
    from handover.copilot.router import _provider_of

    assert price_for("openai/gpt-oss-120b") == (Decimal("0"), Decimal("0"))  # groq free
    assert price_for("gpt-4o-mini") == (Decimal("0.15"), Decimal("0.6"))
    assert price_for("claude-sonnet-4") == (Decimal("3"), Decimal("15"))
    assert price_for("totally-unknown-xyz") == (Decimal("0"), Decimal("0"))
    # groq serves vendor-prefixed ids under the groq key
    assert _provider_of("openai/gpt-oss-20b") == "groq"
    assert _provider_of("qwen/qwen3.8-27b") == "groq"
    assert _provider_of("gpt-4o") == "openai"
    assert _provider_of("claude-3-5-sonnet-latest") == "anthropic"  # native
    assert _provider_of("anthropic/claude-3.5-sonnet") == "openrouter"  # via OpenRouter
    assert _provider_of("deepseek-chat") == "deepseek"


def test_load_candidates_parses_state(tmp_path: Path) -> None:
    state = tmp_path / "grade_state.json"
    state.write_text(
        json.dumps(
            {"cards": {
                "gpt-oss-20b": {"provider": "groq", "score": 69.2},
                "some/paid-model": {"grade": 80.0},
            }}
        ),
        encoding="utf-8",
    )
    cands = {c.model_id: c for c in load_candidates(state)}
    assert cands["gpt-oss-20b"].free is True
    assert cands["some/paid-model"].provider == "openrouter"  # vendor ids route via OpenRouter
    assert load_candidates(tmp_path / "missing.json") == []
