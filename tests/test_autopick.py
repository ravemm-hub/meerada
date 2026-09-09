"""⚡ Auto: the Bourse picks the model. Grade data is a fake; nothing is fetched."""

from handover.copilot.autopick import AutoPicker, rank
from handover.copilot.serve import AUTO_ID, Board, provider_for

CARDS = {
    "qwen/qwen3.8-27b": {"score": 77.8, "n": 54, "econ": {"cpat_usd": 0.00005}},
    # same score to the point as qwen, but cheaper per verified task
    "openai/gpt-oss-20b": {"score": 78.2, "n": 54, "econ": {"cpat_usd": 0.00002}},
    "minimax/minimax-m2.7:free": {"score": 72.2, "n": 54, "econ": {"cpat_usd": 0.00024}},
    "groq/compound": {"score": 13.3, "n": 15},
    "gemini-2.5-flash": {"score": 90.0, "n": 12},  # too small a sample to trust
    "openai/gpt-oss-120b": {"score": None, "n": 0},
}


def test_rank_prefers_score_then_price_and_respects_keys() -> None:
    rows = rank(CARDS, ["groq", "openrouter"])
    assert [r[0] for r in rows] == [
        "openai/gpt-oss-20b", "qwen/qwen3.8-27b", "minimax/minimax-m2.7:free"
    ]
    assert rank(CARDS, ["openrouter"]) == [("minimax/minimax-m2.7:free", 72.2, 0.00024)]
    assert rank(CARDS, ["openai"]) == []  # nothing graded runs on an OpenAI key yet


def test_picker_caches_and_survives_outage() -> None:
    calls = {"n": 0}

    def fetch() -> dict:
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("offline")
        return {"cards": CARDS}

    p = AutoPicker(fetch)
    assert p.choose(["groq"], now=100.0) == "openai/gpt-oss-20b"
    assert p.choose(["groq"], now=200.0) == "openai/gpt-oss-20b" and calls["n"] == 1
    assert p.choose(["groq"], now=100.0 + 3601) == "openai/gpt-oss-20b"  # kept last good board
    assert AutoPicker(lambda: {"cards": {}}).choose(["groq"]) is None


class _Completion:
    text = "ok"
    input_tokens = 5
    output_tokens = 2


class _Caller:
    def __init__(self) -> None:
        self.models: list[str] = []

    def complete(self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int):
        self.models.append(model)
        return _Completion()


def test_board_auto_routes_to_the_picked_model_and_says_so() -> None:
    caller = _Caller()
    board = Board(lambda _m: caller, pick_auto=lambda: "openai/gpt-oss-20b")
    out = board.send("s1", AUTO_ID, "hello")
    assert out["model"] == "openai/gpt-oss-20b" and out["auto"] is True and out["error"] is None
    assert caller.models == ["openai/gpt-oss-20b"]
    assert board.describe("s1")["model"] == "openai/gpt-oss-20b"
    # no grade data reachable -> honest error, never a crash
    dead = Board(lambda _m: caller, pick_auto=lambda: None)
    assert "no graded model" in dead.send("s2", AUTO_ID, "hello")["error"]


def test_provider_for_prefers_a_connected_provider_for_shared_ids() -> None:
    assert provider_for("openai/gpt-4o-mini", connected=["openrouter"]) == "openrouter"
    assert provider_for("openai/gpt-4o-mini", connected=["github"]) == "github"
    assert provider_for("openai/gpt-4o-mini") == "github"  # catalog order when nothing connected
    assert provider_for("gemini-2.5-flash", connected=["google"]) == "google"
    assert provider_for("unknown/thing", {"unknown/thing": "openrouter"}) == "openrouter"


def test_board_counts_model_switches_per_month() -> None:
    caller = _Caller()
    board = Board(lambda _m: caller)
    board.send("s1", "a", "hi")
    board.send("s1", "b", "hi")  # switch 1
    board.send("s1", "a", "hi")  # switch 2
    board.send("s2", "a", "hi")  # new session, not a switch
    assert board.switches == 2 and board.switch_month
