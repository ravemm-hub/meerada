"""Watch Claude Code (and Codex-style JSONL logs) live, beside the tool.

Claude Code appends one JSON record per turn to
``~/.claude/projects/<slug>/<session>.jsonl``. The watcher tails every file
that is still being written, turns records into guard :class:`Event`s (tokens,
thinking, cost from the model's list price, tool calls, verifiable progress
such as a file edit or a passing test run), runs the stall detector per
session and the cage on every tool call, and alerts on state changes. The user
does nothing: no proxy, no key, no change to how they work.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from handover.copilot.pricing import price_for
from handover.guard.alerts import Alert, Sink
from handover.guard.cage import decision, inspect_outbound
from handover.guard.policy import Policy
from handover.guard.signals import Event, StallDetector, Verdict

_PROGRESS_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_PASS = re.compile(
    r"(?i)\b(\d+ passed|all tests passed|tests? ok|build succeeded|exit code 0|OK)\b"
)
_FRESH_S = 6 * 3600  # only files touched in the last 6h are "live" sessions


@dataclass
class Tracked:
    path: Path
    offset: int = 0
    detector: StallDetector | None = None
    model: str = ""
    cwd: str = ""
    last_state: str = "ok"
    title: str = ""
    spent: float = 0.0
    buf: str = field(default="")
    seen: set[tuple[str, str]] = field(default_factory=set)  # cage findings already alerted


def _blocks(rec: dict[str, Any]) -> list[dict[str, Any]]:
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def _ts(rec: dict[str, Any], fallback: float) -> float:
    raw = rec.get("timestamp")
    if isinstance(raw, (int, float)):
        return float(raw) / (1000 if raw > 1e12 else 1)
    if isinstance(raw, str) and raw:
        try:
            from datetime import datetime

            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return fallback


def events_from_record(
    rec: dict[str, Any], *, now: float, model_hint: str = ""
) -> tuple[list[Event], str, str]:
    """(events, model, cwd) for one JSONL record. Unknown record types -> no events."""
    kind = rec.get("type")
    ts = _ts(rec, now)
    cwd = str(rec.get("cwd") or "")
    if kind == "assistant":
        msg = rec.get("message") or {}
        model = str(msg.get("model") or model_hint)
        usage = msg.get("usage") or {}
        out = int(usage.get("output_tokens") or 0)
        cached = int(usage.get("cache_read_input_tokens") or 0)
        inp = int(usage.get("input_tokens") or 0) + int(
            usage.get("cache_creation_input_tokens") or 0
        )
        think = int((usage.get("output_tokens_details") or {}).get("thinking_tokens") or 0)
        pin, pout = price_for(model) if model else (0, 0)
        cost = (float(inp + cached * 0.1) * float(pin) + float(out) * float(pout)) / 1_000_000
        text = " ".join(str(b.get("text", "")) for b in _blocks(rec) if b.get("type") == "text")
        evs = [
            Event(
                ts=ts,
                kind="assistant",
                out_tokens=out,
                in_tokens=inp,
                thinking_tokens=think,
                cost_usd=cost,
                text=text,
            )
        ]
        for b in _blocks(rec):
            if b.get("type") == "tool_use":
                name = str(b.get("name") or "")
                args = json.dumps(b.get("input") or {}, sort_keys=True)[:600]
                evs.append(
                    Event(
                        ts=ts,
                        kind="tool",
                        tool=name,
                        tool_args=args,
                        progress=name in _PROGRESS_TOOLS,
                    )
                )
        return evs, model, cwd
    if kind == "user":
        blocks = _blocks(rec)
        if any(b.get("type") == "tool_result" for b in blocks):
            body = json.dumps([b.get("content") for b in blocks if b.get("type") == "tool_result"])
            return (
                [Event(ts=ts, kind="progress", progress=bool(_PASS.search(body)))],
                model_hint,
                cwd,
            )
        return (
            [Event(ts=ts, kind="user", progress=True)],
            model_hint,
            cwd,
        )  # a human spoke: new task
    return [], model_hint, cwd


def _strings(v: Any) -> list[str]:
    """Every string inside a tool input, raw (no JSON escaping to confuse paths)."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _strings(x)]
    return []


def tool_text(rec: dict[str, Any]) -> str:
    """Outbound text of a record's tool calls (for the cage)."""
    parts: list[str] = []
    for b in _blocks(rec):
        if b.get("type") == "tool_use":
            parts.extend(_strings(b.get("input") or {}))
    return "\n".join(parts)


class ClaudeCodeWatcher:
    def __init__(
        self,
        policy: Policy,
        sink: Sink,
        *,
        home: Path | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._p = policy
        self._sink = sink
        self._root = (home or Path.home()) / ".claude" / "projects"
        self._clock = clock
        self.tracked: dict[Path, Tracked] = {}

    # ------------------------------------------------------------ discovery --
    def _live_files(self) -> list[Path]:
        now = self._clock()
        try:
            files = list(self._root.glob("*/*.jsonl"))
        except OSError:
            return []
        return [f for f in files if now - f.stat().st_mtime < _FRESH_S]

    def _track(self, path: Path) -> Tracked:
        t = self.tracked.get(path)
        if t is None:
            t = Tracked(
                path=path, offset=path.stat().st_size
            )  # start at the end: only NEW activity
            self.tracked[path] = t
        return t

    # ----------------------------------------------------------------- tick --
    def tick(self) -> list[Verdict]:
        """Read what's new in every live session; return current verdicts."""
        out: list[Verdict] = []
        for path in self._live_files():
            t = self._track(path)
            self._drain(t)
            if t.detector is not None:
                v = t.detector.check(self._clock())
                self._announce(t, v)
                out.append(v)
        return out

    def _drain(self, t: Tracked) -> None:
        try:
            with t.path.open("rb") as fh:
                fh.seek(t.offset)
                chunk = fh.read()
                t.offset = fh.tell()
        except OSError:
            return
        if not chunk:
            return
        t.buf += chunk.decode("utf-8", "replace")
        lines = t.buf.split("\n")
        t.buf = lines.pop()  # a partial last line waits for the next tick
        for line in lines:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            self._ingest(t, rec)

    def _ingest(self, t: Tracked, rec: dict[str, Any]) -> None:
        if rec.get("type") == "custom-title":
            t.title = str(rec.get("title") or rec.get("customTitle") or t.title)
        evs, model, cwd = events_from_record(rec, now=self._clock(), model_hint=t.model)
        t.model, t.cwd = model or t.model, cwd or t.cwd
        if not evs:
            return
        if t.detector is None:
            t.detector = StallDetector(self._p)
        for ev in evs:
            t.detector.observe(ev)
            t.spent += ev.cost_usd
        if rec.get("type") == "assistant":
            found = inspect_outbound(tool_text(rec), self._p, cwd=Path(t.cwd) if t.cwd else None)
            findings = [f for f in found if (f.kind, f.snippet) not in t.seen]  # once per session
            t.seen.update((f.kind, f.snippet) for f in findings)
            if findings:
                what = "; ".join(f"{f.what} ({f.snippet})" for f in findings[:4])
                level = "blocked" if decision(findings) == "block" else "warn"
                self._sink.send(
                    Alert(
                        level,
                        "cage: the model is reaching outside the workspace",
                        what,
                        session=self._label(t),
                        ts=self._clock(),
                    )
                )

    def _label(self, t: Tracked) -> str:
        return (
            t.title or t.path.parent.name.replace("-", "/").strip("/")[-40:] + "/" + t.path.stem[:8]
        )

    def _announce(self, t: Tracked, v: Verdict) -> None:
        if v.state == t.last_state:
            return
        t.last_state = v.state
        if v.state in ("stalled", "burning"):
            title = (
                "Claude Code task looks stuck"
                if v.state == "stalled"
                else "Claude Code task is burning money"
            )
            self._sink.send(
                Alert(
                    v.state,
                    title,
                    "; ".join(v.reasons) + f" · ${v.spent_usd:.2f} this task",
                    session=self._label(t),
                    ts=self._clock(),
                )
            )
        elif v.state == "watch" and v.working_hard:
            self._sink.send(
                Alert(
                    "warn",
                    "working hard — watch the budget",
                    "; ".join(v.reasons),
                    session=self._label(t),
                    ts=self._clock(),
                )
            )

    def snapshot(self) -> list[dict[str, Any]]:
        now = self._clock()
        rows = []
        for t in self.tracked.values():
            if t.detector is None:
                continue
            rows.append(
                {
                    "session": self._label(t),
                    "model": t.model,
                    "cwd": t.cwd,
                    **t.detector.check(now).as_dict(),
                }
            )
        return rows

    def run(
        self,
        *,
        interval_s: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        stop: Callable[[], bool] = lambda: False,
    ) -> None:
        while not stop():
            self.tick()
            sleep(interval_s)
