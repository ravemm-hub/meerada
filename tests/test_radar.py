"""Deprecation radar: urgency from an injected date, replacement grade deltas,
and actionable filtering."""

from datetime import date
from pathlib import Path

from handover.radar import (
    Deprecation,
    actionable,
    build_radar,
    load_deprecations,
    render_radar,
)

SEED = Path(__file__).parent.parent / "data" / "deprecations_seed.json"


def test_radar_page_renders_self_contained(tmp_path: Path) -> None:
    deps = load_deprecations(SEED)
    today = date(2026, 8, 29)
    entries = build_radar(
        deps, today, grades={"gpt-5.6-terra": 78.0, "gpt-4-legacy-snapshots": 60.0}
    )
    out = render_radar(entries, tmp_path / "radar.html", today=today)
    html = out.read_text(encoding="utf-8")
    assert "Deprecation Radar" in html
    assert "meerada pack" in html  # the CTA
    assert "gpt-5.6-terra" in html and "+18" in html  # grade delta shown
    assert 'src="http' not in html and 'href="http' not in html  # self-contained


def dep(model_id: str, retires: str, status: str, reps: list[str]) -> Deprecation:
    return Deprecation(
        provider="p",
        model_id=model_id,
        retires_on=date.fromisoformat(retires),
        status=status,
        replacements=tuple(reps),
    )


def test_urgency_buckets_from_reference_date() -> None:
    today = date(2026, 9, 1)
    deps = [
        dep("m-critical", "2026-09-20", "deprecated", []),  # 19 days
        dep("m-soon", "2026-11-01", "deprecated", []),  # 61 days
        dep("m-watch", "2027-01-01", "deprecated", []),  # 122 days
        dep("m-clear", "2027-06-01", "deprecated", []),  # 273 days
        dep("m-retired", "2026-08-01", "retired", []),  # past
    ]
    by_id = {e.model_id: e for e in build_radar(deps, today)}
    assert by_id["m-critical"].urgency == "critical"
    assert by_id["m-soon"].urgency == "soon"
    assert by_id["m-watch"].urgency == "watch"
    assert by_id["m-clear"].urgency == "clear"
    assert by_id["m-retired"].urgency == "retired"
    assert by_id["m-critical"].days_left == 19


def test_sorted_soonest_actionable_first_retired_last() -> None:
    today = date(2026, 9, 1)
    deps = [
        dep("retired", "2026-01-01", "retired", []),
        dep("soon", "2026-11-01", "deprecated", []),
        dep("critical", "2026-09-10", "deprecated", []),
    ]
    order = [e.model_id for e in build_radar(deps, today)]
    assert order == ["critical", "soon", "retired"]


def test_replacement_grade_delta() -> None:
    today = date(2026, 9, 1)
    deps = [dep("old", "2026-10-01", "deprecated", ["new-a", "new-b"])]
    grades = {"old": 70.0, "new-a": 82.5, "new-b": 68.0}
    entry = build_radar(deps, today, grades=grades)[0]
    by_model = {r.model_id: r for r in entry.replacements}
    assert by_model["new-a"].grade == 82.5
    assert by_model["new-a"].grade_delta == 12.5  # upgrade
    assert by_model["new-b"].grade_delta == -2.0  # downgrade — flagged honestly


def test_replacement_without_grade_data_is_none() -> None:
    today = date(2026, 9, 1)
    entry = build_radar([dep("old", "2026-10-01", "deprecated", ["new"])], today)[0]
    assert entry.replacements[0].grade is None
    assert entry.replacements[0].grade_delta is None


def test_actionable_filters_to_ninety_days() -> None:
    today = date(2026, 9, 1)
    deps = [
        dep("critical", "2026-09-10", "deprecated", []),
        dep("soon", "2026-11-15", "deprecated", []),
        dep("watch", "2027-02-01", "deprecated", []),
        dep("retired", "2026-01-01", "retired", []),
    ]
    ids = {e.model_id for e in actionable(build_radar(deps, today))}
    assert ids == {"critical", "soon"}


def test_seed_file_loads_and_builds() -> None:
    deps = load_deprecations(SEED)
    assert len(deps) >= 5
    entries = build_radar(deps, date(2026, 8, 29))
    assert all(e.days_left is not None for e in entries)
    # Everything in the seed with a past date must read as retired.
    for entry in entries:
        if entry.days_left < 0:
            assert entry.urgency == "retired"
