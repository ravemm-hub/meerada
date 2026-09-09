"""⚡ Auto — the Bourse decides which model answers.

The live grade board (grade_state.json, published hourly) is the exchange's
price list: verified quality per model, with CPAT. ``AutoPicker`` reads it
(cached an hour, from the public site or a local file) and picks the
top-graded, cheapest-per-task model whose provider the user has connected —
so a session on "auto" is always on the best free model that clears the bar,
and moves when the board moves. Never raises: no data means no pick, and the
caller falls back to an explicit model.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from handover.copilot.router import _provider_of

GRADE_URLS = (
    "https://meerada.app/grade_state.json",
    "https://ravemm-hub.github.io/meerada/grade_state.json",
)
CACHE_TTL_S = 3600
MIN_N = 30  # same publishable bar as the board
MIN_SCORE = 60.0


def _fetch_state() -> dict[str, Any]:
    last: Exception = RuntimeError("no grade url")
    for url in GRADE_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "meerada/0.2"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data: dict[str, Any] = json.loads(resp.read().decode())
                return data
        except Exception as exc:  # try the next origin
            last = exc
    raise last


def rank(cards: dict[str, Any], connected: Sequence[str]) -> list[tuple[str, float, float]]:
    """(model_id, score, cpat) for runnable, publishable cards — best first:
    highest score, then lowest cost per verified task."""
    rows: list[tuple[str, float, float]] = []
    for model_id, card in cards.items():
        if not isinstance(card, dict):
            continue
        score = card.get("score")
        if score is None or int(card.get("n") or 0) < MIN_N or float(score) < MIN_SCORE:
            continue
        if _provider_of(str(model_id)) not in connected:
            continue
        econ = card.get("econ") or {}
        cpat = float(econ.get("cpat_usd") or 0.0)
        rows.append((str(model_id), float(score), cpat))
    rows.sort(key=lambda r: (-round(r[1]), r[2]))  # score to the point, then price
    return rows


class AutoPicker:
    def __init__(
        self,
        fetch: Callable[[], dict[str, Any]] = _fetch_state,
        local: Path | None = None,
    ) -> None:
        self._fetch = fetch
        self._local = local
        self._cards: dict[str, Any] = {}
        self._at: float | None = None

    def cards(self, *, now: float | None = None) -> dict[str, Any]:
        now = time.time() if now is None else now
        if self._at is None or now - self._at > CACHE_TTL_S:
            data: dict[str, Any] = {}
            try:
                data = self._fetch()
            except Exception:
                if self._local and self._local.exists():
                    try:
                        data = json.loads(self._local.read_text(encoding="utf-8"))
                    except ValueError:
                        data = {}
            if isinstance(data, dict) and isinstance(data.get("cards"), dict):
                self._cards = data["cards"]
            self._at = now
        return self._cards

    def choose(self, connected: Sequence[str], *, now: float | None = None) -> str | None:
        ranked = rank(self.cards(now=now), connected)
        return ranked[0][0] if ranked else None
