"""LLManager's living model list — new models reach the picker by themselves.

The static catalog is the curated core. On top of it, when the user has an
OpenRouter key connected, we merge the public OpenRouter feed: everything that
launched in the last three weeks ("🆕"), every free variant, and the current
flagship of each big lab — so a stealth model like Ox Alpha is selectable the
day it appears, on the user's own key. Fetched at most once an hour; an
unreachable feed just means the static catalog.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from handover.bench.discover_web import LiveModel, fetch_live

CACHE_TTL_S = 3600
# Big-lab flagships worth listing even when not new (one per vendor, by prefix).
_FLAGSHIP_HINTS = ("anthropic/claude", "openai/gpt", "google/gemini", "x-ai/grok", "deepseek/")
_MAX_LIVE = 40


def _fmt_price(m: LiveModel) -> str:
    if m.free:
        return "free"
    return f"${m.price_in:g}/${m.price_out:g} per M"


def _tag(m: LiveModel) -> str:
    bits = []
    if m.is_new:
        bits.append("🆕 new")
    bits.append(_fmt_price(m))
    if "image" in m.modalities:
        bits.append("vision")
    if m.context >= 1_000_000:
        bits.append("1M ctx")
    return " · ".join(bits)


def live_catalog_entries(models: list[LiveModel]) -> list[dict[str, str]]:
    """Picker rows (id/name/provider/tag) from the live feed: new first, then
    free, then one flagship per big lab. Capped so the picker stays usable."""
    seen: set[str] = set()
    rows: list[dict[str, str]] = []

    def add(m: LiveModel) -> None:
        if m.id in seen or len(rows) >= _MAX_LIVE:
            return
        seen.add(m.id)
        rows.append({"id": m.id, "name": m.name, "provider": "openrouter", "tag": _tag(m)})

    for m in models:
        if m.is_new:
            add(m)
    for m in models:
        if m.free:
            add(m)
    flagged: set[str] = set()
    for m in models:
        for hint in _FLAGSHIP_HINTS:
            if m.id.startswith(hint) and hint not in flagged and not m.free:
                flagged.add(hint)
                add(m)
    return rows


class LiveCatalog:
    """Hourly-cached live entries. ``fetch`` is injectable for tests."""

    def __init__(self, fetch: Callable[[], list[LiveModel]] = fetch_live) -> None:
        self._fetch = fetch
        self._rows: list[dict[str, str]] = []
        self._at: float | None = None

    def entries(self, *, now: float | None = None) -> list[dict[str, str]]:
        now = time.time() if now is None else now
        if self._at is None or now - self._at > CACHE_TTL_S:
            models = self._fetch()
            if models:
                self._rows = live_catalog_entries(models)
            self._at = now
        return list(self._rows)
