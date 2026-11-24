"""Answers kept verbatim, as JSON next to the page on gh-pages (like grade_state.json).

One record per (engine, query, ask); the newest per pair is what the page
shows, older ones stay for the history. Which queries a tick asks is
round-robin by age, so every pair is refreshed at the same pace.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from handover.visibility.questions import Query

STATE_VERSION = 1
MAX_ANSWERS = 50 * 4 * 30  # every pair, a month of history


class Answer(BaseModel):
    engine: str
    model: str
    query_id: str
    asked_at: datetime
    text: str
    citations: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    name_keys: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    cost_usd: str = "0"
    input_tokens: int = 0
    output_tokens: int = 0
    searches: int = 0
    error: str | None = None


class State(BaseModel):
    version: int = STATE_VERSION
    answers: list[Answer] = Field(default_factory=list)
    skipped: dict[str, str] = Field(default_factory=dict)  # engine -> why no key

    def latest(self) -> dict[tuple[str, str], Answer]:
        """Newest *successful* answer per (engine, query); an error never hides an
        older good answer, but a pair with only errors is kept so the page says so."""
        out: dict[tuple[str, str], Answer] = {}
        for a in self.answers:
            k = (a.engine, a.query_id)
            cur = out.get(k)
            if (
                cur is None
                or (cur.error and not a.error)
                or (bool(cur.error) == bool(a.error) and a.asked_at >= cur.asked_at)
            ):
                out[k] = a
        return out

    def add(self, answer: Answer) -> None:
        self.answers.append(answer)
        if len(self.answers) > MAX_ANSWERS:
            del self.answers[: len(self.answers) - MAX_ANSWERS]


def load_state(path: Path) -> State:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return State()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not raw:
        return State()
    return State.model_validate(raw)


def save_state(state: State, path: Path) -> None:
    path.write_text(state.model_dump_json(indent=1), encoding="utf-8")


def pick_queries(state: State, engine: str, queries: tuple[Query, ...], k: int) -> list[Query]:
    """The ``k`` queries this engine has gone longest without — never asked first,
    then oldest ask; errors count as asked so a broken pair does not starve the rest."""
    last: dict[str, datetime] = {}
    for a in state.answers:
        if a.engine == engine:
            prev = last.get(a.query_id)
            if prev is None or a.asked_at > prev:
                last[a.query_id] = a.asked_at
    floor = datetime(1970, 1, 1, tzinfo=UTC)
    position = {q.id: i for i, q in enumerate(queries)}
    ordered = sorted(queries, key=lambda q: (last.get(q.id, floor), position[q.id]))
    return ordered[: max(0, k)]
