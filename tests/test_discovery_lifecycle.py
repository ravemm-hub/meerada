"""Continuous, near-real-time grading: detect new/upgraded models, grade them
provisionally, and tighten to confirmed as the sample grows."""

from datetime import UTC, datetime, timedelta

from handover.bench import (
    CatalogModel,
    classify,
    diff_catalog,
    next_cadence,
    to_grade,
)
from handover.metrics.core import proportion

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def cat(model_id: str, version: str = "v1", provider: str = "p") -> CatalogModel:
    return CatalogModel(provider=provider, model_id=model_id, version_hint=version)


def test_new_model_detected() -> None:
    current = [cat("m-old"), cat("m-new")]
    known = {"m-old": "v1"}
    changes = diff_catalog(current, known)
    new = [c for c in changes if c.change == "new"]
    assert [c.model_id for c in new] == ["m-new"]
    assert new[0].needs_grading is True
    assert to_grade(changes) == ["m-new"]


def test_silent_upgrade_detected() -> None:
    current = [cat("m", version="2026-08-29")]
    known = {"m": "2026-06-01"}
    (change,) = diff_catalog(current, known)
    assert change.change == "upgraded"
    assert change.previous_version == "2026-06-01"
    assert change.current_version == "2026-08-29"
    assert change.needs_grading is True


def test_removed_model_flagged_last_and_not_graded() -> None:
    current = [cat("stays")]
    known = {"stays": "v1", "gone": "v1"}
    changes = diff_catalog(current, known)
    assert changes[-1].model_id == "gone" and changes[-1].change == "removed"
    assert "gone" not in to_grade(changes)


def test_new_and_upgraded_sort_before_removed() -> None:
    current = [cat("upg", version="v2"), cat("fresh")]
    known = {"upg": "v1", "old": "v1"}
    order = [(c.model_id, c.change) for c in diff_catalog(current, known)]
    assert order == [("fresh", "new"), ("upg", "upgraded"), ("old", "removed")]


def test_small_sample_is_provisional() -> None:
    card = classify("m", 82.0, proportion(28, 30), NOW, NOW)
    assert card.status == "provisional"
    assert card.n == 30
    assert card.ci_width_points is not None and card.ci_width_points > 0
    assert card.is_publishable is True  # provisional shows, labelled


def test_below_provisional_floor_not_publishable() -> None:
    card = classify("m", 90.0, proportion(9, 10), NOW, NOW)
    assert card.is_publishable is False  # n < 30 -> never ranked


def test_large_fresh_sample_is_confirmed_with_tight_ci() -> None:
    provisional = classify("m", 82.0, proportion(28, 30), NOW, NOW)
    confirmed = classify("m", 82.0, proportion(560, 640), NOW, NOW)
    assert confirmed.status == "confirmed"
    # More samples -> tighter interval, the whole point of the ladder.
    assert confirmed.ci_width_points < provisional.ci_width_points


def test_old_confirmed_grade_goes_stale() -> None:
    old = NOW - timedelta(hours=60)
    card = classify("m", 82.0, proportion(560, 640), old, NOW)
    assert card.status == "stale"
    assert card.is_publishable is False


def test_next_cadence_advances_confidence() -> None:
    provisional = classify("m", 82.0, proportion(28, 30), NOW, NOW)
    confirmed = classify("m", 82.0, proportion(560, 640), NOW, NOW)
    stale = classify("m", 82.0, proportion(560, 640), NOW - timedelta(hours=60), NOW)
    assert next_cadence(provisional) == "daily"  # push toward confirmed
    assert next_cadence(confirmed) == "weekly"  # hold
    assert next_cadence(stale) == "daily"  # refresh
