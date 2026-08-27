"""T16 tests: property-based checks against known distributions, the §6.1
sample-size table, CUSUM behaviour, and Benjamini-Hochberg FDR."""

import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from handover.canary import (
    Cusum,
    benjamini_hochberg,
    normal_cdf,
    normal_ppf,
    power_two_proportions,
    sample_size_two_proportions,
    two_proportion_p_value,
)


def test_normal_ppf_known_values() -> None:
    assert normal_ppf(0.5) == pytest.approx(0.0, abs=1e-9)
    assert normal_ppf(0.975) == pytest.approx(1.959964, abs=1e-4)
    assert normal_ppf(0.95) == pytest.approx(1.644854, abs=1e-4)
    assert normal_ppf(0.8) == pytest.approx(0.841621, abs=1e-4)


@given(st.floats(min_value=0.001, max_value=0.999))
def test_ppf_and_cdf_are_inverses(p: float) -> None:
    assert normal_cdf(normal_ppf(p)) == pytest.approx(p, abs=1e-6)


def test_sample_size_matches_spec_table() -> None:
    # SPEC §6.1 practical numbers for p = 0.90: 15pt→~70, 10pt→~150, 5pt→~570, 2pt→~3400.
    for delta, expected in [(0.15, 70), (0.10, 150), (0.05, 570), (0.02, 3400)]:
        n = sample_size_two_proportions(0.90, delta)
        assert expected * 0.75 <= n <= expected * 1.25, (delta, n)


@given(
    st.floats(min_value=0.55, max_value=0.98),
    st.floats(min_value=0.02, max_value=0.2),
)
def test_sample_size_properties(p_base: float, delta: float) -> None:
    if delta >= p_base:
        return
    n = sample_size_two_proportions(p_base, delta)
    assert n >= 1
    # Smaller effects need more samples.
    if delta / 2 < p_base:
        assert sample_size_two_proportions(p_base, delta / 2) > n


def test_power_of_computed_sample_size_hits_target() -> None:
    n = sample_size_two_proportions(0.90, 0.10, power=0.8)
    achieved = power_two_proportions(n, 0.90, 0.10)
    assert achieved == pytest.approx(0.8, abs=0.05)


def test_two_proportion_p_value_sanity() -> None:
    # Identical proportions: p-value near 1; a huge gap: near 0.
    assert two_proportion_p_value(90, 100, 90, 100) == pytest.approx(1.0)
    assert two_proportion_p_value(40, 100, 90, 100) < 1e-6
    # Symmetric in direction for two-sided.
    assert two_proportion_p_value(80, 100, 90, 100) == pytest.approx(
        two_proportion_p_value(90, 100, 80, 100)
    )


def test_cusum_detects_sustained_drop_and_stays_quiet_under_null() -> None:
    rng = random.Random(7)
    # Null: hourly pass rates around the 0.90 target (n=30 canary noise).
    quiet = Cusum(target=0.90, drift=0.10, threshold=0.5)
    false_alarms = sum(
        quiet.update(sum(rng.random() < 0.90 for _ in range(30)) / 30) for _ in range(500)
    )
    assert false_alarms / 500 < 0.02

    # A real 15-point crash must alarm within a handful of windows.
    crash = Cusum(target=0.90, drift=0.10, threshold=0.5)
    windows_to_alarm = None
    for window in range(1, 50):
        rate = sum(rng.random() < 0.75 for _ in range(30)) / 30
        if crash.update(rate):
            windows_to_alarm = window
            break
    assert windows_to_alarm is not None and windows_to_alarm <= 15


def test_benjamini_hochberg_known_example() -> None:
    # Hand-computed: thresholds i/m*q = .01,.02,.03,.04,.05 -> ranks 1-3 pass,
    # ranks 4-5 (p=.5,.6) fail, so the cutoff is rank 3.
    p_values = [0.01, 0.5, 0.02, 0.6, 0.03]
    rejected = benjamini_hochberg(p_values, q=0.05)
    assert rejected == [True, False, True, False, True]

    # The step-up property: a large p late in rank order can rescue smaller ones.
    stepped = benjamini_hochberg([0.04, 0.049], q=0.05)
    assert stepped == [True, True]  # rank 2 threshold 0.05 >= 0.049 rescues rank 1


def test_benjamini_hochberg_controls_false_discoveries_under_null() -> None:
    rng = random.Random(11)
    total_rejections = 0
    rounds = 50
    for _ in range(rounds):
        nulls = [rng.random() for _ in range(480)]  # 40 models x 12 clusters
        total_rejections += sum(benjamini_hochberg(nulls, q=0.05))
    # Naive alpha=0.05 would flag ~24 per round; BH under the global null
    # keeps the family-wise rate near q, so rejections are rare.
    assert total_rejections / rounds < 1.0


def test_benjamini_hochberg_finds_real_signals_among_nulls() -> None:
    rng = random.Random(3)
    signals = [1e-8, 1e-7, 1e-6]
    nulls = [rng.uniform(0.2, 1.0) for _ in range(97)]
    rejected = benjamini_hochberg(signals + nulls, q=0.05)
    assert rejected[:3] == [True, True, True]
    assert sum(rejected[3:]) == 0


def test_benjamini_hochberg_empty() -> None:
    assert benjamini_hochberg([]) == []
