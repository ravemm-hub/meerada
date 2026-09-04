"""The Handshake inside LLManager: import any history, move it between models,
attach files, compose models. Parsers are pure; the Board uses fake callers."""
# ruff: noqa: E501  (export fixtures are long JSON literals)

import json
from pathlib import Path

from handover.copilot import importers as imp
from handover.copilot.serve import Board


class FakeCompletion:
    def __init__(self, text: str) -> None:
        self.text = text
        self.input_tokens = 20
        self.output_tokens = 8


class RecordingCaller:
    """Remembers what it was asked so tests can assert the history travelled."""

    def __init__(self, model: str) -> None:
        self.model = model
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    def complete(self, model: str, system: str, messages: list[dict[str, str]], max_tokens: int):
        self.calls.append((system, messages))
        return FakeCompletion(f"reply from {model}")


CALLERS: dict[str, RecordingCaller] = {}


def _caller_for(model_id: str) -> RecordingCaller:
    return CALLERS.setdefault(model_id, RecordingCaller(model_id))


def _jsonl(*records: dict) -> str:
    return "\n".join(json.dumps(r) for r in records)


# ------------------------------------------------------------------ parsers --
def test_claude_code_jsonl_keeps_the_thread_and_drops_noise() -> None:
    text = _jsonl(
        {"type": "summary", "summary": "Fix the login bug"},
        {"type": "queue-operation", "operation": "enqueue"},
        {"type": "user", "isSidechain": False, "cwd": "C:/proj/app", "timestamp": "2026-09-01T10:00:00Z",
         "message": {"role": "user", "content": "why does login 500?<system-reminder>ignore me</system-reminder>"}},
        {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
            {"type": "thinking", "thinking": "secret"},
            {"type": "text", "text": "Let me look."},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "auth.py"}}]}},
        {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [
            {"type": "tool_result", "content": "def login(): ..." * 500}]}},
        {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
            {"type": "text", "text": "The token check is inverted on line 12."}]}},
        {"type": "user", "isSidechain": True, "message": {"role": "user", "content": "subagent noise"}},
    )
    conv = imp.parse_claude_code_jsonl(text, path="C:/u/.claude/projects/C--proj-app/abc.jsonl")
    assert conv.source == "claude-code"
    assert conv.title == "Fix the login bug"
    assert conv.meta["project"] == "app" and conv.meta["when"] == "2026-09-01"
    assert [t["role"] for t in conv.turns] == ["user", "assistant"]
    assert conv.turns[0]["content"] == "why does login 500?"
    a = conv.turns[1]["content"]
    assert "secret" not in a and "[used Read" in a and "inverted on line 12" in a
    assert "subagent noise" not in a
    assert len(a) < 2000  # the giant tool result was trimmed


def test_normalise_alternates_and_trims_oldest() -> None:
    turns = [
        {"role": "assistant", "content": "leading junk"},
        {"role": "user", "content": "a"}, {"role": "user", "content": "b"},
        {"role": "assistant", "content": "c"},
        {"role": "user", "content": "d"},
    ]
    norm = imp.normalise(turns)
    assert norm == [{"role": "user", "content": "a\n\nb"}, {"role": "assistant", "content": "c"}]
    long = [{"role": r, "content": "x" * 100} for r in ["user", "assistant"] * 10]
    trimmed = imp.normalise(long, max_chars=450)
    assert len(trimmed) == 4 and trimmed[0]["content"].startswith("[imported — 8 earlier")


def test_claude_ai_and_chatgpt_exports_detect() -> None:
    claude = json.dumps([{"name": "Trip plan", "created_at": "2026-05-01T00:00:00Z", "chat_messages": [
        {"sender": "human", "text": "plan rome"}, {"sender": "assistant", "text": "day 1: colosseum"}]}])
    convs = imp.detect_and_parse(claude, "conversations.json")
    assert len(convs) == 1 and convs[0].source == "claude-ai" and convs[0].title == "Trip plan"
    assert convs[0].turns[1]["content"] == "day 1: colosseum"

    chatgpt = json.dumps([{"title": "Regex help", "create_time": 1780000000, "current_node": "n3", "mapping": {
        "n1": {"message": {"author": {"role": "system"}, "content": {"parts": ["sys"]}}, "parent": None, "children": ["n2"]},
        "n2": {"message": {"author": {"role": "user"}, "content": {"parts": ["match emails"]}}, "parent": "n1", "children": ["n3", "n4"]},
        "n3": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["use \\S+@\\S+"]}}, "parent": "n2", "children": []},
        "n4": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["OLD BRANCH"]}}, "parent": "n2", "children": []},
    }}])
    convs = imp.detect_and_parse(chatgpt, "conversations.json")
    assert convs[0].source == "chatgpt" and convs[0].title == "Regex help"
    assert [t["content"] for t in convs[0].turns] == ["match emails", "use \\S+@\\S+"]  # current branch only


def test_transcript_and_plain_notes() -> None:
    conv = imp.detect_and_parse("User: hi\nAssistant: hello\nUser: more\nAssistant: sure", "chat.md")[0]
    assert conv.source == "transcript" and len(conv.turns) == 4
    notes = imp.detect_and_parse("just my notes\nabout the project", "notes.txt")[0]
    assert notes.turns[0]["role"] == "user" and "just my notes" in notes.turns[0]["content"]
    assert imp.detect_and_parse("", "x.txt") == []


def test_scan_and_path_guard(tmp_path: Path) -> None:
    proj = tmp_path / ".claude" / "projects" / "C--Users-me-proj"
    proj.mkdir(parents=True)
    (proj / "s1.jsonl").write_text(_jsonl(
        {"type": "user", "isSidechain": False, "timestamp": "2026-09-02T00:00:00Z",
         "message": {"role": "user", "content": "first question"}},
        {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": "answer"}},
    ), encoding="utf-8")
    (proj / "empty.jsonl").write_text('{"type":"summary","summary":"nothing"}', encoding="utf-8")
    found = imp.scan_claude_code(tmp_path)
    assert len(found) == 1 and found[0]["title"] == "first question" and found[0]["turns"] == 1
    assert found[0]["project"] == "proj" and found[0]["when"] == "2026-09-02"  # from the slug
    assert imp.is_under_claude_root(found[0]["path"], tmp_path)
    assert not imp.is_under_claude_root(str(tmp_path / "secrets.txt"), tmp_path)


def test_read_folder_skips_vendor_and_binary(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "b.js").write_text("x", encoding="utf-8")
    (tmp_path / "img.png").write_bytes(b"\x89PNG")
    files, report = imp.read_folder(str(tmp_path))
    assert [f["name"] for f in files] == ["src/a.py"]
    assert report["skipped_binary"] == 1 and report["files"] == 1
    assert "<file path=\"src/a.py\">" in imp.context_block(files)


# -------------------------------------------------------------------- board --
def test_import_then_switch_model_carries_history() -> None:
    CALLERS.clear()
    board = Board(_caller_for)
    turns = [{"role": "user", "content": "we chose postgres"}, {"role": "assistant", "content": "good choice"}]
    view = board.import_conversation("s1", "claude-x", turns, title="DB design", source="claude-code")
    assert view["turns"] == 1 and view["title"] == "DB design" and view["source"] == "claude-code"
    r = board.send("s1", "gpt-y", "remind me what we chose")  # continue on ANOTHER model
    assert r["turns"] == 2
    _system, messages = CALLERS["gpt-y"].calls[-1]
    assert messages[0]["content"] == "we chose postgres"  # the history travelled
    assert board.describe("s1")["title"] == "DB design"  # so did the title


def test_fork_copies_conversation_to_second_model() -> None:
    CALLERS.clear()
    board = Board(_caller_for)
    board.send("s1", "a", "task")
    view = board.fork("s1", "s2", "b")
    assert view["id"] == "s2" and view["model"] == "b" and view["turns"] == 1
    board.send("s2", "b", "go on")
    assert CALLERS["b"].calls[-1][1][1]["content"] == "reply from a"  # a's answer travelled
    assert board.describe("s1")["turns"] == 1  # original untouched
    assert "no history" in board.fork("nope", "s3", "b")["error"]
    assert sorted(s["id"] for s in board.overview()) == ["s1", "s2"]


def test_attach_files_go_to_system_and_travel_on_handshake() -> None:
    CALLERS.clear()
    board = Board(_caller_for)
    view = board.attach("s1", "a", [{"name": "app.py", "text": "def main(): pass"}, {"name": "", "text": "  "}])
    assert view["attachments"] == ["app.py"] and view["context_chars"] == len("def main(): pass")
    board.send("s1", "a", "explain")
    system, messages = CALLERS["a"].calls[-1]
    assert '<file path="app.py">' in system and "def main" in system
    assert all("def main" not in m["content"] for m in messages)  # not in the chat itself
    board.send("s1", "b", "and now?")  # switch model: attachments travel too
    assert "def main" in CALLERS["b"].calls[-1][0]


def test_judge_ranks_across_sessions_in_its_own_session() -> None:
    CALLERS.clear()
    board = Board(_caller_for)
    board.send("s1", "a", "what is 2+2")
    board.send("s2", "b", "what is 2+2")
    out = board.judge(["s1", "s2", "ghost"], "j1", "c")
    assert out["error"] is None and out["text"] == "reply from c"
    assert [j["model"] for j in out["judged"]] == ["a", "b"]
    prompt = CALLERS["c"].calls[-1][1][-1]["content"]
    assert "ANSWER 1 (from a)" in prompt and "reply from b" in prompt and "BEST ANSWER" in prompt
    assert board.describe("j1")["title"] == "⚖️ Verdict"
    assert "no answers" in board.judge(["nothing"], "j2", "c")["error"]


def test_relay_drafts_cheap_then_polishes() -> None:
    CALLERS.clear()
    board = Board(_caller_for)
    out = board.relay("s1", "strong", "cheap", "write a haiku")
    assert out["error"] is None and out["text"] == "reply from strong"
    assert out["relay"]["draft_model"] == "cheap"
    polish_prompt = CALLERS["strong"].calls[-1][1][-1]["content"]
    assert "reply from cheap" in polish_prompt  # the draft was handed over
    hist = board.history("s1")
    assert hist[0]["content"] == "write a haiku" and len(hist) == 2  # visible history stays clean
    assert out["total_tokens"] == 2 * 28  # both calls counted on the ledger


def test_provider_errors_become_actionable() -> None:
    from urllib.error import HTTPError, URLError

    from handover.copilot.session import friendly_error

    http = HTTPError("https://api.openai.com/v1/chat/completions", 429, "Too Many Requests", {}, None)  # type: ignore[arg-type]
    assert friendly_error(http).startswith("429 — rate limit on YOUR provider account")
    assert "reconnect" in friendly_error(HTTPError("u", 401, "Unauthorized", {}, None))  # type: ignore[arg-type]
    assert friendly_error(URLError("getaddrinfo failed")).startswith("network")
    assert friendly_error(TimeoutError("timed out")).startswith("timeout")
    assert friendly_error(ValueError("weird")) == "ValueError: weird"


def test_preview_board_refuses_handshake_ops_gracefully() -> None:
    board = Board(None)
    assert "connect a key" in board.import_conversation("s", "m", [], title="t", source="x")["error"]
    assert "connect a key" in board.attach("s", "m", [])["error"]
    assert "connect a key" in board.relay("s", "m", "d", "msg")["error"]
