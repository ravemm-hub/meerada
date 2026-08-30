"""Cockpit view functions: pure, injected, no live API (CLAUDE.md).
The FastAPI/uvicorn shell is a network seam and is not exercised here."""

from handover.copilot.serve import Board, chat_view, optimize_view, run_view
from handover.copilot.session import SessionManager


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


def test_chat_view_persists_turns_across_calls() -> None:
    manager = SessionManager(_caller_for)
    first = chat_view(manager, {"message": "hello", "models": ["a", "b"]})
    assert first["live"] is True
    assert {r["model"] for r in first["results"]} == {"a", "b"}
    assert all(r["turns"] == 1 for r in first["results"])
    second = chat_view(manager, {"message": "again", "models": ["a", "b"]})
    # the same manager -> history accumulates to a second turn per model
    assert all(r["turns"] == 2 for r in second["results"])
    assert all(r["total_tokens"] > 0 for r in second["results"])


def test_chat_view_preview_when_no_manager() -> None:
    out = chat_view(None, {"message": "do x as json", "models": ["a"]})
    assert out["live"] is False
    assert "preview only" in out["results"][0]["error"]


def test_chat_view_rejects_empty() -> None:
    assert chat_view(SessionManager(_caller_for), {"message": "", "models": ["a"]})["results"] == []


def test_board_sessions_are_independent() -> None:
    board = Board(_caller_for)
    # two sessions on the SAME model, different tasks — histories must not mix
    board.send("s1", "llama", "task one")
    board.send("s2", "llama", "task two")
    r1 = board.send("s1", "llama", "follow up")
    assert r1["turns"] == 2  # s1 has its own two turns
    assert board.send("s2", "llama", "x")["turns"] == 2  # s2 tracked separately
    assert set(board.sessions) == {"s1", "s2"}


def test_board_model_change_rehomes_session() -> None:
    board = Board(_caller_for)
    board.send("s1", "llama", "hi")
    r = board.send("s1", "gemma", "hi again")  # switched model -> fresh session
    assert r["model"] == "gemma"
    assert r["turns"] == 1


def test_board_preview_and_close() -> None:
    preview = Board(None).send("s1", "claude", "do x")
    assert "preview only" in preview["error"]
    board = Board(_caller_for)
    board.send("s1", "llama", "hi")
    board.close("s1")
    assert "s1" not in board.sessions


def test_board_rejects_incomplete() -> None:
    assert "required" in Board(_caller_for).send("", "llama", "hi")["error"]
    assert "required" in Board(_caller_for).send("s1", "llama", "")["error"]
