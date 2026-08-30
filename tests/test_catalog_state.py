"""Live catalog parsing (fake fetch), and state persistence across ticks."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from handover.bench.catalog import fetch_catalog, parse_models
from handover.bench.continuous import initial_state, tick
from handover.bench.discovery import CatalogModel
from handover.bench.lifecycle import classify
from handover.bench.state_store import load_state, save_state
from handover.metrics.core import proportion
from handover.replay.budget import DailyBudget

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def test_parse_openai_models_body() -> None:
    body = {"data": [{"id": "gpt-5.6-luna", "created": 1_760_000_000}, {"id": ""}, {"nope": 1}]}
    models = parse_models("openai", body)
    assert [m.model_id for m in models] == ["gpt-5.6-luna"]
    assert models[0].version_hint == "1760000000"


def test_fetch_catalog_skips_keyless_and_erroring_providers() -> None:
    def raw(base: str, key: str) -> dict:
        if "groq" in base:
            return {"data": [{"id": "llama-x", "created": 1}]}
        raise RuntimeError("provider down")

    models = fetch_catalog(
        ["groq", "openai", "mistral"],
        {"groq": "k", "openai": "", "mistral": "k"},  # openai keyless, mistral errors
        raw_fetch=raw,
    )
    assert [m.model_id for m in models] == ["llama-x"]


def test_state_round_trips(tmp_path: Path) -> None:
    state = initial_state({"m": "v1"})
    state.cards["m"] = classify("m", 82.0, proportion(600, 640), NOW, NOW)
    path = tmp_path / "state.json"
    save_state(path, state)

    loaded = load_state(path)
    assert loaded.known_versions == {"m": "v1"}
    assert loaded.cards["m"].status == "confirmed"
    assert loaded.cards["m"].score == 82.0


def test_missing_state_file_is_empty(tmp_path: Path) -> None:
    loaded = load_state(tmp_path / "nope.json")
    assert loaded.cards == {} and loaded.known_versions == {}


def test_persisted_state_advances_on_next_tick(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    save_state(path, initial_state())

    def fetch() -> list[CatalogModel]:
        return [CatalogModel(provider="p", model_id="m", version_hint="v1")]

    def grade(model_id: str) -> tuple[float, object]:
        return 80.0, proportion(28, 30)

    state = load_state(path)
    state, _ = tick(state, fetch, grade, DailyBudget(Decimal("100")), NOW)
    save_state(path, state)

    reloaded = load_state(path)
    assert reloaded.cards["m"].status == "provisional"
    assert reloaded.known_versions == {"m": "v1"}
