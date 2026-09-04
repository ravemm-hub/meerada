"""Web discovery → exchange queue → LLManager picker. Feed bodies are fakes."""
# ruff: noqa: E501  (feed fixtures are long literals)

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from handover.bench import discover_web as dw
from handover.bench.continuous_run import _gradable
from handover.bench.discovery import CatalogModel
from handover.bench.prices import price_for_model
from handover.copilot.catalog_live import LiveCatalog, live_catalog_entries

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
DAY = 86400
T0 = int(NOW.timestamp())


def _item(mid: str, days_ago: int, p_in: float, p_out: float, **kw: object) -> dict:
    return {
        "id": mid, "name": kw.get("name", mid), "created": T0 - days_ago * DAY,
        "context_length": kw.get("ctx", 128000),
        "pricing": {"prompt": str(p_in / 1e6), "completion": str(p_out / 1e6)},
        "architecture": {"input_modalities": kw.get("mods", ["text"])},
    }


BODY = {"data": [
    _item("z-ai/glm-5.3-flash", 9, 0.075, 0.25, name="Z.ai: GLM 5.3 Flash (Ox Alpha)", ctx=1310720, mods=["text", "image"]),
    _item("z-ai/glm-5.3-flash:batch", 9, 0.15, 0.5),
    _item("~z-ai/glm-flash-latest", 8, 0.075, 0.25),
    _item("z-ai/glm-5.2:free", 60, 0, 0),
    _item("anthropic/claude-fable-5.1", 3, 10, 50, ctx=1000000),
    _item("anthropic/claude-opus-5", 200, 5, 25),
    _item("google/gemini-3.8-flash", 2, 0.75, 3.75),
    _item("meta/muse-spark-1.3", 2, 1.25, 4.25),
    _item("old/thing", 400, 1, 2),
]}


def test_parse_drops_aliases_flags_free_and_new() -> None:
    models = dw.parse_openrouter(BODY, now=NOW)
    ids = [m.id for m in models]
    assert "z-ai/glm-5.3-flash:batch" not in ids and "~z-ai/glm-flash-latest" not in ids
    ox = next(m for m in models if m.id == "z-ai/glm-5.3-flash")
    assert ox.is_new and ox.age_days == 9 and ox.price_out == 0.25 and ox.modalities == "text+image"
    assert ox.created == "2026-08-26"
    free = dw.free_models(models)
    assert [m.id for m in free] == ["z-ai/glm-5.2:free"] and not free[0].is_new
    assert len(dw.new_models(models)) == 4
    assert models[0].created >= models[-1].created  # newest first


def test_fetch_live_never_raises_and_json_roundtrip(tmp_path: Path) -> None:
    def broken() -> dict:
        raise OSError("offline")

    assert dw.fetch_live(broken) == []
    models = dw.fetch_live(lambda: BODY)
    out = tmp_path / "models_live.json"
    dw.write_json(models, out)
    text = out.read_text(encoding="utf-8")
    assert '"z-ai/glm-5.3-flash"' in text and '"count": 7' in text


def test_prices_prefer_live_feed_and_price_free_at_paid_sibling() -> None:
    live = dw.live_prices(dw.parse_openrouter(BODY, now=NOW))
    assert price_for_model("z-ai/glm-5.3-flash", live) == (Decimal("0.075"), Decimal("0.25"), "list")
    # a :free variant is priced at what it costs at scale — its paid sibling
    live["z-ai/glm-5.2"] = (0.5, 1.5)
    assert price_for_model("z-ai/glm-5.2:free", live)[1] == Decimal("1.5")
    # unknown everywhere -> static table / estimate, never crashes
    assert price_for_model("nobody/knows", live)[2] == "estimated"
    assert price_for_model("openai/gpt-oss-20b", {})[2] == "list"


def test_openrouter_grading_is_free_only_unless_opted_in() -> None:
    free = CatalogModel(provider="openrouter", model_id="z-ai/glm-5.2:free")
    paid = CatalogModel(provider="openrouter", model_id="z-ai/glm-5.3-flash")
    groq = CatalogModel(provider="groq", model_id="openai/gpt-oss-20b")
    tts = CatalogModel(provider="groq", model_id="playai-tts")
    assert _gradable(free, False) and not _gradable(paid, False) and _gradable(groq, False)
    assert _gradable(paid, True)
    assert not _gradable(tts, True)


def test_live_catalog_entries_new_first_then_free_then_flagships() -> None:
    rows = live_catalog_entries(dw.parse_openrouter(BODY, now=NOW))
    ids = [r["id"] for r in rows]
    assert ids[:4] == ["google/gemini-3.8-flash", "meta/muse-spark-1.3", "anthropic/claude-fable-5.1", "z-ai/glm-5.3-flash"]
    assert "z-ai/glm-5.2:free" in ids and "old/thing" not in ids
    assert ids.count("anthropic/claude-fable-5.1") == 1  # flagship not duplicated
    ox = next(r for r in rows if r["id"] == "z-ai/glm-5.3-flash")
    assert ox["provider"] == "openrouter" and ox["tag"].startswith("🆕 new · $0.075/$0.25 per M")
    assert "vision" in ox["tag"] and "1M ctx" in ox["tag"]
    free_row = next(r for r in rows if r["id"].endswith(":free"))
    assert free_row["tag"] == "free"


def test_live_catalog_caches_for_an_hour_and_survives_outage() -> None:
    calls = {"n": 0}

    def fetch() -> list[dw.LiveModel]:
        calls["n"] += 1
        return dw.parse_openrouter(BODY, now=NOW) if calls["n"] == 1 else []

    cat = LiveCatalog(fetch)
    first = cat.entries(now=1000.0)
    assert len(first) == 5 and calls["n"] == 1
    cat.entries(now=1500.0)
    assert calls["n"] == 1  # cached
    again = cat.entries(now=1000.0 + 3601)
    assert calls["n"] == 2 and len(again) == 5  # outage -> keeps the last good list
