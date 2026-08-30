"""Cockpit view functions: pure, injected, no live API (CLAUDE.md).
The FastAPI/uvicorn shell is a network seam and is not exercised here."""

from handover.copilot.serve import optimize_view, run_view


class FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text
        self.input_tokens = 15
        self.output_tokens = 6


class FakeCaller:
    def complete(self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int):
        return FakeCompletion(f"reply from {model}")


def _caller_for(_model_id: str) -> FakeCaller:
    return FakeCaller()


def test_optimize_view_returns_lean_prompt_per_model() -> None:
    payload = {"intent": "please extract the fields as json", "models": ["claude", "gpt"]}
    out = optimize_view(payload)
    assert [r["model"] for r in out["results"]] == ["claude", "gpt"]
    for row in out["results"]:
        assert row["optimized_tokens"] < row["naive_tokens"]
        assert row["saved_pct"] > 0
        assert "ONLY valid JSON" in row["system"]


def test_run_view_live_fans_out() -> None:
    out = run_view({"intent": "summarise this", "models": ["a", "b"]}, _caller_for)
    assert out["live"] is True
    assert [r["model"] for r in out["results"]] == ["a", "b"]
    assert out["results"][0]["text"] == "reply from a"
    assert all(r["error"] is None for r in out["results"])


def test_run_view_preview_when_no_caller() -> None:
    out = run_view({"intent": "do x as json", "models": ["a"]}, None)
    assert out["live"] is False
    row = out["results"][0]
    assert row["text"] == ""
    assert "preview only" in row["error"]
    assert row["saved_pct"] > 0  # still shows the saving


def test_run_view_rejects_empty() -> None:
    assert run_view({"intent": "", "models": ["a"]}, _caller_for)["results"] == []
    assert run_view({"intent": "x", "models": []}, _caller_for)["results"] == []
