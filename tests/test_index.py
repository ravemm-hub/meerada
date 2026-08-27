"""T18 tests: within-cluster-only normalization, weight sensitivity, and the
static index page with embedded slider payload."""

from pathlib import Path

import pytest

from handover.branding import BRAND_NAME
from handover.metrics import compute_core
from handover.metrics.index import Weights, cluster_axis_norms, compute_index
from handover.report.index_page import render_index
from tests.factories import make_task


def metrics(success_n: int, total: int, cost: str, wall_ms: int):
    return compute_core(
        [make_task(succeeded=i < success_n, cost=cost, wall_ms=wall_ms) for i in range(total)]
    )


PER_CLUSTER = {
    # c01: model-a better quality, model-b cheaper.
    "c01": {
        "model-a": metrics(95, 100, "0.20", 60000),
        "model-b": metrics(85, 100, "0.02", 30000),
    },
    # c02: reversed.
    "c02": {
        "model-a": metrics(70, 100, "0.20", 60000),
        "model-b": metrics(95, 100, "0.02", 30000),
    },
}
SHARES = {"c01": 0.7, "c02": 0.3}


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        Weights(quality=0.9, speed=0.2, value=0.2)


def test_normalization_is_within_cluster_only() -> None:
    norms_c01 = cluster_axis_norms("c01", PER_CLUSTER["c01"])
    # Within one cluster the best model gets 1.0 and the worst 0.0 on each axis.
    by_model = {n.model_id: n for n in norms_c01}
    assert by_model["model-a"].quality == 1.0
    assert by_model["model-b"].quality == 0.0
    assert by_model["model-b"].value == 1.0  # cheaper -> better value

    # Adding an absurdly expensive cluster elsewhere must not change c01's norms.
    other = {"c99": {"model-a": metrics(99, 100, "9999", 1)}}
    again = cluster_axis_norms("c01", PER_CLUSTER["c01"])
    assert norms_c01 == again, other  # trivially unchanged: computed per cluster


def test_index_respects_cost_share_weighting() -> None:
    entries = compute_index(PER_CLUSTER, SHARES)
    assert entries[0].model_id in {"model-a", "model-b"}
    assert all(e.score is not None for e in entries)
    assert all(set(e.cluster_scores) == {"c01", "c02"} for e in entries)


def test_weights_change_the_ranking() -> None:
    quality_first = compute_index(PER_CLUSTER, SHARES, Weights(quality=1.0, speed=0.0, value=0.0))
    value_first = compute_index(PER_CLUSTER, SHARES, Weights(quality=0.0, speed=0.0, value=1.0))
    # All-in on value must crown the cheap model.
    assert value_first[0].model_id == "model-b"
    # And the two extreme weightings disagree about someone's score.
    assert quality_first[0].score != value_first[0].score


def test_index_page_renders_with_sliders(tmp_path: Path) -> None:
    out = render_index(PER_CLUSTER, SHARES, tmp_path / "index.html")
    html = out.read_text(encoding="utf-8")
    assert BRAND_NAME in html
    assert 'input type="range"' in html
    assert '"cost_shares"' in html and '"norms"' in html  # embedded payload
    assert "model-b" in html
    assert 'src="http' not in html and 'href="http' not in html  # self-contained
