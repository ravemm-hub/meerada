"""Find new models on the open web and queue them for the exchange.

OpenRouter publishes a public catalog (no key needed) of ~400 models across
every lab, with prices, context and a creation stamp — the best single feed
for "what just launched" (stealth/alpha models show up there first). We
normalise it into ``LiveModel`` rows that the Arena's "New on the market"
band, the grader's pricing and LLManager's picker all read. The HTTP call is
the only seam; tests inject a body.

    python -m handover.bench.discover_web --out site/models_live.json
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
NEW_DAYS = 21  # "new on the market" window
RawFetch = Callable[[], dict[str, Any]]


@dataclass(frozen=True)
class LiveModel:
    id: str
    name: str
    vendor: str
    price_in: float  # USD per 1M input tokens
    price_out: float
    context: int
    created: str  # ISO date
    age_days: int
    free: bool
    modalities: str  # e.g. "text+image"

    @property
    def is_new(self) -> bool:
        return self.age_days <= NEW_DAYS


def _urllib_fetch() -> dict[str, Any]:
    req = urllib.request.Request(OPENROUTER_MODELS_URL, headers={"User-Agent": "meerada/0.2"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body: dict[str, Any] = json.loads(resp.read().decode())
        return body


def parse_openrouter(body: dict[str, Any], *, now: datetime | None = None) -> list[LiveModel]:
    """Normalise an OpenRouter /models body. Batch/alias variants (``:batch``,
    ``~vendor/…-latest``) are dropped; ``:free`` variants are kept and flagged."""
    now = now or datetime.now(tz=UTC)
    out: list[LiveModel] = []
    for item in body.get("data", []):
        mid = str(item.get("id") or "").strip()
        if not mid or mid.startswith("~") or mid.endswith(":batch"):
            continue
        pricing = item.get("pricing") or {}
        try:
            p_in = float(pricing.get("prompt") or 0) * 1e6
            p_out = float(pricing.get("completion") or 0) * 1e6
        except (TypeError, ValueError):
            p_in = p_out = 0.0
        created_ts = int(item.get("created") or 0)
        created = datetime.fromtimestamp(created_ts, tz=UTC) if created_ts else now
        arch = item.get("architecture") or {}
        mods = arch.get("input_modalities") or ["text"]
        out.append(
            LiveModel(
                id=mid,
                name=str(item.get("name") or mid),
                vendor=mid.split("/", 1)[0],
                price_in=round(p_in, 4),
                price_out=round(p_out, 4),
                context=int(item.get("context_length") or 0),
                created=created.strftime("%Y-%m-%d"),
                age_days=max(0, (now - created).days),
                free=mid.endswith(":free") or (p_in == 0 and p_out == 0),
                modalities="+".join(str(m) for m in mods),
            )
        )
    out.sort(key=lambda m: m.created, reverse=True)
    return out


def fetch_live(raw_fetch: RawFetch = _urllib_fetch) -> list[LiveModel]:
    """Best effort: an unreachable feed yields an empty list, never an exception."""
    try:
        return parse_openrouter(raw_fetch())
    except Exception:
        return []


def live_prices(models: list[LiveModel]) -> dict[str, tuple[float, float]]:
    """id -> (in, out) list prices, USD per 1M tokens, for the grader's pricing."""
    return {m.id: (m.price_in, m.price_out) for m in models}


def new_models(models: list[LiveModel], days: int = NEW_DAYS) -> list[LiveModel]:
    return [m for m in models if m.age_days <= days]


def free_models(models: list[LiveModel]) -> list[LiveModel]:
    return [m for m in models if m.free]


def write_json(models: list[LiveModel], path: Path) -> None:
    payload = {
        "generated_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "source": "openrouter public catalog",
        "count": len(models),
        "new_days": NEW_DAYS,
        "models": [asdict(m) for m in models],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="handover.bench.discover_web")
    parser.add_argument("--out", type=Path, default=Path("out/models_live.json"))
    args = parser.parse_args(argv)
    models = fetch_live()
    if not models:
        print("discovery: feed unreachable — kept the previous file")
        return 1
    write_json(models, args.out)
    fresh = new_models(models)
    print(
        f"discovery: {len(models)} models, {len(fresh)} new in {NEW_DAYS}d, "
        f"{len(free_models(models))} free -> {args.out}"
    )
    for m in fresh[:12]:
        flag = "  FREE" if m.free else ""
        print(f"  {m.created} {m.id:44} ${m.price_in:.3f}/${m.price_out:.3f}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
