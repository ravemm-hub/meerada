"""scripts/build_feeds.py: badges, the RSS feed and the Meerada Index from published data."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_feeds", ROOT / "scripts" / "build_feeds.py")
assert spec and spec.loader
bf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bf)


def _card(mid: str, score: float, n: int = 40, cpat: float | None = 0.002) -> dict[str, object]:
    return {
        "model_id": mid,
        "score": score,
        "n": n,
        "status": "confirmed",
        "history": [score - 1, score],
        "econ": {"cpat_usd": cpat} if cpat is not None else None,
        "updated_at": "2026-09-16T10:00",
    }


def test_build_writes_badges_index_and_feed(tmp_path: Path) -> None:
    state = tmp_path / "grade_state.json"
    state.write_text(
        json.dumps(
            {
                "cards": {
                    "openai/gpt-oss-120b": _card("openai/gpt-oss-120b", 70.0),
                    "qwen/qwen3.8-27b": _card("qwen/qwen3.8-27b", 30.6, cpat=None),
                    "tiny": _card("tiny", 90.0, n=3),  # n<30 -> not published, no badge
                }
            }
        ),
        encoding="utf-8",
    )
    live = tmp_path / "models_live.json"
    live.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "z-ai/glm-5.3-flash",
                        "vendor": "z-ai",
                        "age_days": 2,
                        "price_in": 0.1,
                        "price_out": 0.3,
                        "context": 128000,
                    },
                    {"id": "old/model", "vendor": "old", "age_days": 200},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "site"
    res = bf.build(state, live, out)
    assert res == {"badges": 2, "index_members": 2}
    svg = (out / "badges" / "openai_gpt-oss-120b.svg").read_text(encoding="utf-8")
    assert "#1" in svg and "70.0" in svg and "$0.0020/task" in svg and "<svg" in svg
    idx = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert (
        idx["value"] == 50.3
        and idx["median_cpat_usd"] == 0.002
        and idx["members"][0] == "openai/gpt-oss-120b"
    )
    xml = (out / "feed.xml").read_text(encoding="utf-8")
    assert (
        "<rss" in xml
        and "gpt-oss-120b: grade 70.0 (+1.0)" in xml
        and "New model: z-ai/glm-5.3-flash" in xml
    )
    assert "old/model" not in xml and "tiny" not in xml


def test_empty_state_is_fine(tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert bf.build(tmp_path / "none.json", tmp_path / "none2.json", out) == {
        "badges": 0,
        "index_members": 0,
    }
    assert json.loads((out / "index.json").read_text(encoding="utf-8"))["value"] is None
