"""Bring your history with you — import conversations from any assistant.

The Handshake, inside the manager: a conversation that started in Claude Code,
Claude.ai, ChatGPT (or any transcript) becomes a live LLManager session, and the
user can continue it on ANY model with the whole history carried over. These
parsers are pure (text in, turns out) and never touch the network; the local
``~/.claude`` scan is the only filesystem seam and is exercised with a tmp dir.

Supported sources (auto-detected):
  * Claude Code   — ``~/.claude/projects/<slug>/<session>.jsonl``
  * Claude.ai     — data export ``conversations.json`` (chat_messages / sender)
  * ChatGPT       — data export ``conversations.json`` (mapping tree / author.role)
  * transcript    — ``User:`` / ``Assistant:`` style markdown or plain text
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Keep an imported history within a sane prompt budget: every later turn re-sends
# it to the model (on the user's tokens). Oldest turns are dropped first.
MAX_HISTORY_CHARS = 120_000
# Tool payloads (file dumps, command output) are noise for a chat handoff — trim.
MAX_TOOL_CHARS = 400
_ASSISTANT_ROLES = {"assistant", "model", "ai", "claude", "chatgpt", "gpt", "bot"}
# Harness-injected blocks are not the user's words.
_HARNESS_TAGS = (
    r"<(system-reminder|local-command-caveat|task-notification|command-name|command-message"
    r"|command-args|local-command-stdout|ci-monitor-event)>.*?</\1>"
)
_TYPE_USER = re.compile(r'"type":\s*"user"')
_SIDECHAIN = re.compile(r'"isSidechain":\s*true')
_USER_ROLES = {"user", "human", "you", "me"}


@dataclass
class Conversation:
    """One imported conversation: alternating user/assistant turns, normalised."""

    title: str
    source: str  # claude-code | claude-ai | chatgpt | transcript
    turns: list[dict[str, str]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def chars(self) -> int:
        return sum(len(t["content"]) for t in self.turns)

    def summary(self, index: int = 0) -> dict[str, Any]:
        return {
            "i": index,
            "title": self.title,
            "source": self.source,
            "turns": len(self.turns) // 2,
            "chars": self.chars,
            "est_tokens": self.chars // 4,
            **{k: v for k, v in self.meta.items() if k in ("project", "when", "path")},
        }


# ----------------------------------------------------------------- normalise --
def normalise(
    turns: list[dict[str, str]], *, max_chars: int = MAX_HISTORY_CHARS
) -> list[dict[str, str]]:
    """Make a turn list every provider accepts: strict user/assistant alternation,
    starts with user, ends with assistant, consecutive same-role turns merged,
    empties dropped, and the OLDEST turns trimmed to fit ``max_chars``."""
    merged: list[dict[str, str]] = []
    for t in turns:
        role = "assistant" if t.get("role", "").lower() in _ASSISTANT_ROLES else "user"
        content = str(t.get("content", "")).strip()
        if not content:
            continue
        if merged and merged[-1]["role"] == role:
            merged[-1] = {"role": role, "content": merged[-1]["content"] + "\n\n" + content}
        else:
            merged.append({"role": role, "content": content})
    while merged and merged[0]["role"] != "user":
        merged.pop(0)
    while merged and merged[-1]["role"] != "assistant":
        merged.pop()
    total = sum(len(t["content"]) for t in merged)
    dropped = 0
    while merged and total > max_chars and len(merged) > 2:
        total -= len(merged[0]["content"]) + len(merged[1]["content"])
        merged = merged[2:]  # drop the oldest user+assistant pair
        dropped += 1
    if merged and len(merged[0]["content"]) > max_chars:  # a single giant turn
        merged[0]["content"] = merged[0]["content"][-max_chars:]
    if dropped:
        note = f"[imported — {dropped} earlier exchange(s) omitted to fit the prompt budget]\n\n"
        merged[0] = {"role": "user", "content": note + merged[0]["content"]}
    return merged


def _text_of(content: Any) -> str:
    """Flatten a message content (str or list of blocks) into readable text.
    Tool calls/results are summarised in one line so the handoff keeps the
    thread of work without dragging megabytes of file dumps along."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _text_of([content])
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if not isinstance(block, dict):
            continue
        kind = block.get("type", "")
        if kind == "text":
            parts.append(str(block.get("text", "")))
        elif kind == "tool_use":
            name = block.get("name", "tool")
            inp = json.dumps(block.get("input", {}), ensure_ascii=False)
            parts.append(f"[used {name}: {inp[:MAX_TOOL_CHARS]}]")
        elif kind == "tool_result":
            body = _text_of(block.get("content", ""))
            if body:
                parts.append(f"[tool result: {body[:MAX_TOOL_CHARS]}]")
        elif kind == "thinking":
            continue  # private reasoning never travels
        elif "text" in block:
            parts.append(str(block["text"]))
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------- Claude Code --
def parse_claude_code_jsonl(text: str, *, path: str = "") -> Conversation:
    """One ``~/.claude/projects/<proj>/<id>.jsonl`` session -> Conversation."""
    turns: list[dict[str, str]] = []
    title = ""
    cwd = ""
    when = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        kind = rec.get("type")
        if kind == "summary" and not title:
            title = str(rec.get("summary", ""))[:120]
            continue
        if kind not in ("user", "assistant"):
            continue
        if rec.get("isSidechain") or rec.get("isMeta"):
            continue  # subagent chatter / harness meta, not the user's thread
        msg = rec.get("message") or {}
        content = _text_of(msg.get("content"))
        # Harness-injected reminders are not the user's words.
        content = re.sub(_HARNESS_TAGS, "", content, flags=re.S).strip()
        if not content:
            continue
        if (
            kind == "user" and content.startswith("[tool result:")
            and turns and turns[-1]["role"] == "assistant"
        ):
            # fold tool results into the assistant's own turn as a work note
            turns[-1]["content"] += "\n" + content
            continue
        turns.append({"role": kind, "content": content})
        cwd = cwd or str(rec.get("cwd", ""))
        when = when or str(rec.get("timestamp", ""))[:10]
    if not title:
        first = next((t["content"] for t in turns if t["role"] == "user"), "")
        fallback = Path(path).stem[:12] or "Claude Code session"
        title = first.splitlines()[0][:80] if first else fallback
    project = Path(cwd).name if cwd else Path(path).parent.name.replace("-", "/")[:40]
    return Conversation(
        title=title, source="claude-code", turns=normalise(turns),
        meta={"project": project, "when": when, "path": path, "cwd": cwd},
    )


def claude_code_root(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".claude" / "projects"


def scan_claude_code(home: Path | None = None, *, limit: int = 60) -> list[dict[str, Any]]:
    """List Claude Code sessions on THIS machine, newest first (metadata only —
    the transcript is parsed when the user picks one). Local mode only."""
    root = claude_code_root(home)
    if not root.is_dir():
        return []
    files = sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for p in files[:limit]:
        title, first_user, when, cwd = "", "", "", ""
        n_user = 0
        try:
            with p.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    head = line[:400]
                    if '"summary"' in head and not title:
                        with contextlib.suppress(ValueError):
                            title = str(json.loads(line).get("summary", ""))[:120]
                    elif _TYPE_USER.search(head) and not _SIDECHAIN.search(head):
                        n_user += 1
                        if not first_user:
                            try:
                                rec = json.loads(line)
                                first_user = _text_of((rec.get("message") or {}).get("content"))
                                when = str(rec.get("timestamp", ""))[:10]
                                cwd = str(rec.get("cwd", ""))
                            except ValueError:
                                pass
        except OSError:
            continue
        first_user = re.sub(r"<[^>]+>.*?</[^>]+>", "", first_user, flags=re.S).strip()
        if n_user == 0:
            continue
        project = Path(cwd).name if cwd else p.parent.name.split("-")[-1]
        out.append(
            {
                "path": str(p),
                "project": project[:48],
                "title": title or (first_user.splitlines()[0][:80] if first_user else p.stem[:12]),
                "turns": n_user,
                "when": when,
                "size_kb": p.stat().st_size // 1024,
            }
        )
    return out


def is_under_claude_root(path: str, home: Path | None = None) -> bool:
    """Only files inside ``~/.claude/projects`` may be read by the importer —
    it is an import feature, not a file-read oracle."""
    try:
        return Path(path).resolve().is_relative_to(claude_code_root(home).resolve())
    except (OSError, ValueError):
        return False


# ------------------------------------------------------------------ Claude.ai --
def parse_claude_ai_export(data: Any) -> list[Conversation]:
    """claude.ai data export: ``conversations.json`` -> every conversation."""
    if isinstance(data, dict):
        data = [data]
    out: list[Conversation] = []
    for conv in data if isinstance(data, list) else []:
        if not isinstance(conv, dict) or "chat_messages" not in conv:
            continue
        turns = []
        for m in conv.get("chat_messages") or []:
            role = "assistant" if str(m.get("sender", "")).lower() in _ASSISTANT_ROLES else "user"
            text = m.get("text") or _text_of(m.get("content"))
            turns.append({"role": role, "content": str(text)})
        norm = normalise(turns)
        if norm:
            out.append(
                Conversation(
                    title=str(conv.get("name") or norm[0]["content"].splitlines()[0][:80]),
                    source="claude-ai", turns=norm,
                    meta={"when": str(conv.get("created_at", ""))[:10]},
                )
            )
    return out


# -------------------------------------------------------------------- ChatGPT --
def parse_chatgpt_export(data: Any) -> list[Conversation]:
    """ChatGPT data export: ``conversations.json`` (a mapping tree per chat).
    Follows the current branch (current_node -> parents) so edits/regenerations
    resolve to what the user actually saw."""
    if isinstance(data, dict):
        data = [data]
    out: list[Conversation] = []
    for conv in data if isinstance(data, list) else []:
        if not isinstance(conv, dict) or "mapping" not in conv:
            continue
        mapping = conv.get("mapping") or {}
        node_id = conv.get("current_node")
        if not node_id:  # fall back to a leaf without children
            for k, v in mapping.items():
                if not (v or {}).get("children"):
                    node_id = k
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        while node_id and node_id in mapping and node_id not in seen:
            seen.add(node_id)
            node = mapping[node_id] or {}
            msg = node.get("message")
            if msg:
                chain.append(msg)
            node_id = node.get("parent")
        chain.reverse()
        turns = []
        for msg in chain:
            role = str(((msg.get("author") or {}).get("role")) or "")
            if role not in ("user", "assistant"):
                continue  # system / tool plumbing
            content = msg.get("content") or {}
            parts = content.get("parts") if isinstance(content, dict) else None
            if parts is None:
                raw = content if isinstance(content, (str, list)) else content.get("text", "")
                text = _text_of(raw)
            else:
                text = "\n".join(
                    p if isinstance(p, str) else str(p.get("text", "")) for p in parts
                    if isinstance(p, (str, dict))
                )
            turns.append({"role": role, "content": text})
        norm = normalise(turns)
        if norm:
            out.append(
                Conversation(
                    title=str(conv.get("title") or norm[0]["content"].splitlines()[0][:80]),
                    source="chatgpt", turns=norm,
                    meta={"when": _epoch_day(conv.get("create_time"))},
                )
            )
    return out


def _epoch_day(ts: Any) -> str:
    try:
        from datetime import UTC, datetime

        return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


# ----------------------------------------------------------------- transcript --
_SPEAKER = re.compile(
    r"^\s*(?:\*\*|#+\s*|>\s*)?(user|you|human|me|assistant|ai|claude|chatgpt|gpt|bot|model)"
    r"(?:\*\*)?\s*[:：]\s*",  # noqa: RUF001  (ascii or full-width colon)
    re.I,
)


def parse_transcript(text: str, *, title: str = "") -> Conversation:
    """``User:`` / ``Assistant:`` style text (what people paste from anywhere).
    With no speaker labels at all, the whole text becomes context the user
    hands to the next model, so pasting notes still works."""
    turns: list[dict[str, str]] = []
    role = ""
    buf: list[str] = []
    for line in text.splitlines():
        m = _SPEAKER.match(line)
        if m:
            if role and buf:
                turns.append({"role": role, "content": "\n".join(buf).strip()})
            role = "assistant" if m.group(1).lower() in _ASSISTANT_ROLES else "user"
            buf = [line[m.end():]]
        else:
            buf.append(line)
    if role and buf:
        turns.append({"role": role, "content": "\n".join(buf).strip()})
    if not turns and text.strip():
        intro = "Here is the material I was working on:\n\n"
        turns = [
            {"role": "user", "content": intro + text.strip()},
            {"role": "assistant", "content": "Got it — I have the material. What next?"},
        ]
    norm = normalise(turns)
    return Conversation(
        title=title or (norm[0]["content"].splitlines()[0][:80] if norm else "transcript"),
        source="transcript", turns=norm,
    )


# --------------------------------------------------------------------- detect --
def detect_and_parse(text: str, filename: str = "") -> list[Conversation]:
    """Sniff the format and return every conversation found (an export can hold
    hundreds; the UI lets the user pick). Never raises on garbage — an empty
    list means 'nothing recognisable'."""
    name = filename.lower()
    stripped = text.lstrip()
    looks_jsonl = stripped.startswith("{") and '"type"' in stripped[:400] and "\n{" in text
    if name.endswith(".jsonl") or looks_jsonl:
        conv = parse_claude_code_jsonl(text, path=filename)
        return [conv] if conv.turns else []
    if stripped.startswith(("[", "{")):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if data is not None:
            sample = data[0] if isinstance(data, list) and data else data
            if isinstance(sample, dict):
                if "chat_messages" in sample:
                    return parse_claude_ai_export(data)
                if "mapping" in sample:
                    return parse_chatgpt_export(data)
                if "messages" in sample:  # generic {messages:[{role,content}]}
                    convs = []
                    for item in data if isinstance(data, list) else [data]:
                        norm = normalise(
                            [{"role": str(m.get("role", "")), "content": _text_of(m.get("content"))}
                             for m in (item.get("messages") or []) if isinstance(m, dict)]
                        )
                        if norm:
                            convs.append(
                                Conversation(
                                    title=str(item.get("title") or norm[0]["content"][:80]),
                                    source="transcript", turns=norm,
                                )
                            )
                    return convs
    conv = parse_transcript(text, title=Path(filename).stem if filename else "")
    return [conv] if conv.turns else []


# --------------------------------------------------------- files & folders ----
TEXT_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".md", ".txt", ".yml", ".yaml", ".toml",
    ".html", ".css", ".scss", ".sql", ".sh", ".ps1", ".bat", ".ini", ".cfg", ".env.example",
    ".rs", ".go", ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php",
    ".xml", ".csv", ".graphql", ".proto", ".vue", ".svelte", ".dart", ".r", ".jl", ".lua",
    ".ipynb", ".tex", ".rst", ".log", ".gitignore", ".dockerfile", ".makefile",
}
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next",
    ".expo", "android", "ios", ".idea", ".vscode", "coverage", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", "target", "out", ".gradle", "Pods",
}
MAX_FILE_CHARS = 60_000
MAX_ATTACH_CHARS = 320_000
MAX_FILES = 200


def read_folder(root: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Walk a local folder into ``[{name, text}]`` attachments (text files only,
    build/vendor dirs skipped, sizes capped). Returns the files and a report of
    what was skipped so the UI can say so honestly. Desktop/local mode only."""
    base = Path(root).expanduser()
    files: list[dict[str, str]] = []
    report = {"files": 0, "skipped_binary": 0, "skipped_big": 0, "skipped_limit": 0, "chars": 0}
    if not base.is_dir():
        return files, report
    for p in sorted(base.rglob("*")):
        if any(part in SKIP_DIRS for part in p.relative_to(base).parts):
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() not in TEXT_EXT and p.name.lower() not in ("dockerfile", "makefile"):
            report["skipped_binary"] += 1
            continue
        if len(files) >= MAX_FILES:
            report["skipped_limit"] += 1
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > MAX_FILE_CHARS:
            report["skipped_big"] += 1
            text = text[:MAX_FILE_CHARS] + f"\n… [truncated, {len(text)} chars total]"
        if report["chars"] + len(text) > MAX_ATTACH_CHARS:
            report["skipped_limit"] += 1
            continue
        files.append({"name": str(p.relative_to(base)).replace("\\", "/"), "text": text})
        report["files"] += 1
        report["chars"] += len(text)
    return files, report


def context_block(files: list[dict[str, str]]) -> str:
    """Render attachments as one clearly delimited block for the system prompt."""
    if not files:
        return ""
    parts = ["The user attached these files; treat them as the working context:"]
    for f in files:
        parts.append(f"\n<file path=\"{f['name']}\">\n{f['text']}\n</file>")
    return "\n".join(parts)
