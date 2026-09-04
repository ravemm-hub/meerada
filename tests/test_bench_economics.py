"""The price side of the exchange: measured CPAT / TTAT travel with the grade."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from handover.bench.continuous import initial_state, tick
from handover.bench.continuous_run import economics
from handover.bench.discovery import CatalogModel
from handover.bench.lifecycle import Economics
from handover.bench.prices import ESTIMATE, list_price
from handover.bench.state_store import load_state, save_state
from handover.metrics.core import PerWinFloat, PerWinMoney, proportion
from handover.replay.budget import DailyBudget

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _metrics(cpat: str, wins: int, ttat: float):
    class M:  # the slice of CoreMetrics that economics() reads
        cpat_usd = PerWinMoney(value=Decimal(cpat), n_successes=wins, n_tasks=wins + 2)
        ttat_seconds = PerWinFloat(value=ttat, n_successes=wins, n_tasks=wins + 2)

    return M()


def test_list_price_longest_match_and_estimate_fallback() -> None:
    assert list_price("openai/gpt-oss-120b")[2] == "list"
    assert list_price("openai/gpt-oss-20b")[0] == Decimal("0.075")
    assert list_price("qwen/qwen3.8-27b")[2] == "estimated"  # priced off qwen3-32b
    assert list_price("qwen/qwen3-32b")[2] == "list"  # longer key wins over 'qwen/qwen3'
    assert list_price("totally-unknown-model") == ESTIMATE


def test_economics_pools_clusters_by_wins() -> None:
    per_cluster = {"a": _metrics("0.0010", 10, 1.0), "b": _metrics("0.0040", 10, 3.0)}
    econ = economics(per_cluster, (Decimal("0.15"), Decimal("0.60"), "list"))  # type: ignore[arg-type]
    assert econ is not None
    assert econ.cpat_usd == 0.0025 and econ.ttat_s == 2.0 and econ.n_successes == 20
    assert econ.price_in == 0.15 and econ.price_note == "list"
    assert economics({"a": _metrics("0.001", 0, 1.0)}, ESTIMATE) is None  # type: ignore[arg-type]


def test_tick_carries_economics_and_accepts_two_tuple_graders() -> None:
    def fetch() -> list[CatalogModel]:
        return [CatalogModel(provider="p", model_id="m", version_hint="v1")]

    econ = Economics(cpat_usd=0.002, ttat_s=1.5, n_successes=20, price_in=0.1, price_out=0.3)
    budget = DailyBudget(Decimal(9))
    state, _ = tick(initial_state(), fetch, lambda _m: (80.0, proportion(28, 30), econ), budget, NOW)
    assert state.cards["m"].econ == econ
    # a plain (score, quality) grader still works, and keeps the prior economics
    state, _ = tick(state, fetch, lambda _m: (81.0, proportion(29, 30)), budget, NOW)
    assert state.cards["m"].econ == econ
    assert state.cards["m"].history == (80.0, 81.0)


def test_state_roundtrip_and_old_state_without_econ_loads(tmp_path: Path) -> None:
    def fetch() -> list[CatalogModel]:
        return [CatalogModel(provider="p", model_id="m", version_hint="v1")]

    econ = Economics(cpat_usd=0.002, ttat_s=1.5, n_successes=20, price_in=0.1, price_out=0.3)
    budget = DailyBudget(Decimal(9))
    state, _ = tick(initial_state(), fetch, lambda _m: (80.0, proportion(28, 30), econ), budget, NOW)
    path = tmp_path / "state.json"
    save_state(path, state)
    assert load_state(path).cards["m"].econ == econ
    # states written before economics existed must still load (econ -> None)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["cards"]["m"]["econ"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_state(path).cards["m"].econ is None
