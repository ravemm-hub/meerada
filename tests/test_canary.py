"""T17 tests: the §6.2 schedule, all four §6.3 alert conditions, the exact
§6.4 alert format, and the 480-null-comparisons false-alert guarantee."""

import random
from datetime import UTC, datetime, timedelta

from handover.canary.drift import Baseline, detect_drift
from handover.canary.scheduler import CADENCE_N, WindowStat, plan_runs

MODELS = ["model-a", "model-b"]
CLUSTERS = [f"c{i:02d}" for i in range(1, 13)]
T0 = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)  # a Monday, 06:00Z


def test_scheduler_pulse_every_hour() -> None:
    runs = plan_runs(MODELS, CLUSTERS, datetime(2026, 8, 26, 14, 0, tzinfo=UTC))
    assert all(r.cadence == "pulse" for r in runs)
    assert len(runs) == len(MODELS)
    assert all(r.n == 30 and r.cluster_id is None for r in runs)


def test_scheduler_daily_at_six_utc() -> None:
    runs = plan_runs(MODELS, CLUSTERS, datetime(2026, 8, 26, 6, 0, tzinfo=UTC))  # Wednesday
    daily = [r for r in runs if r.cadence == "daily"]
    assert len(daily) == len(MODELS) * len(CLUSTERS)
    per_model = sum(r.n for r in daily if r.model_id == "model-a")
    assert per_model == CADENCE_N["daily"]
    assert not [r for r in runs if r.cadence == "weekly"]


def test_scheduler_weekly_on_monday() -> None:
    runs = plan_runs(MODELS, CLUSTERS, T0)  # Monday 06:00Z
    weekly = [r for r in runs if r.cadence == "weekly"]
    assert len(weekly) == len(MODELS) * len(CLUSTERS)
    assert sum(r.n for r in weekly if r.model_id == "model-b") == CADENCE_N["weekly"]


def window(ts_offset_h: int, successes: int, n: int = 610) -> WindowStat:
    return WindowStat(ts=T0 + timedelta(hours=ts_offset_h), n=n, successes=successes)


BASE = Baseline(successes=910, n=1000)  # 0.91


def test_real_drop_alerts_with_exact_format() -> None:
    key = ("Model X", "c07")
    alerts = detect_drift(
        {key: BASE},
        {key: [window(0, 476), window(24, 476)]},  # 0.78 twice
        cluster_labels={"c07": "structured extraction"},
    )
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.confirmed_windows == 2
    text = alert.render()
    assert 'Model Model X · cluster "structured extraction"' in text
    assert "pass rate: 0.91 → 0.78" in text
    assert "Δ = -13.0 pts" in text
    assert "CI95: [" in text
    assert "n = 610" in text
    assert "confirmed over 2 windows" in text
    assert "FDR-adjusted q = 0.00" in text
    assert "first observed: 2026-08-24 06:00Z" in text


def test_single_window_drop_does_not_alert() -> None:
    key = ("m", "c01")
    alerts = detect_drift({key: BASE}, {key: [window(0, 555), window(24, 476)]})
    # Window -2 was healthy (0.91) and one bad window can't cross CUSUM alone.
    assert alerts == []


def test_sustained_small_drift_caught_by_cusum() -> None:
    key = ("m", "c01")
    # Six windows at 0.78: each alone confirms, but pair-confirmation is what
    # fires; here we test the CUSUM path by making the PREVIOUS window healthy
    # yet history long enough for CUSUM to accumulate.
    history = [window(i * 24, 476) for i in range(5)] + [window(120, 555), window(144, 476)]
    alerts = detect_drift({key: BASE}, {key: history})
    assert len(alerts) == 1
    assert alerts[0].cusum_crossed is True
    assert "CUSUM threshold crossed" in alerts[0].render()


def test_insignificant_drop_never_alerts() -> None:
    key = ("m", "c01")
    # 0.89 vs 0.91 baseline: 2 points, below min_effect and CI includes 0.
    alerts = detect_drift({key: BASE}, {key: [window(0, 543), window(24, 543)]})
    assert alerts == []


def test_improvement_never_alerts() -> None:
    key = ("m", "c01")
    alerts = detect_drift({key: BASE}, {key: [window(0, 600), window(24, 600)]})
    assert alerts == []


def test_480_null_comparisons_under_one_alert_per_day() -> None:
    """TASKS T17: 480 simultaneous null comparisons -> fewer than 1 alert/day."""
    rng = random.Random(42)
    pairs = [(f"model-{m:02d}", f"c{c:02d}") for m in range(40) for c in range(12)]
    baselines = {key: Baseline(successes=900, n=1000) for key in pairs}

    days = 20
    total_alerts = 0
    for day in range(days):
        windows = {
            key: [
                WindowStat(
                    ts=T0 + timedelta(days=day, hours=-24),
                    n=600,
                    successes=sum(rng.random() < 0.9 for _ in range(600)),
                ),
                WindowStat(
                    ts=T0 + timedelta(days=day),
                    n=600,
                    successes=sum(rng.random() < 0.9 for _ in range(600)),
                ),
            ]
            for key in pairs
        }
        total_alerts += len(detect_drift(baselines, windows))
    assert total_alerts / days < 1.0
