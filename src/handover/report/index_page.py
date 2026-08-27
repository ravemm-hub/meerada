"""Static index page renderer (SPEC P3): the public grade with weight sliders.

One self-contained HTML file; the §4.3 score recomputes client-side from the
embedded normalized axes when the viewer drags the weights. No network calls;
the local page sends nothing anywhere.
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from handover.branding import BRAND_NAME, GRADE_NAME
from handover.metrics.core import CoreMetrics
from handover.metrics.index import index_payload


def render_index(
    per_cluster: Mapping[str, Mapping[str, CoreMetrics]],
    cost_shares: Mapping[str, float],
    out_path: Path,
    *,
    generated_at: datetime | None = None,
) -> Path:
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("index.html.j2").render(
        brand=BRAND_NAME,
        grade_name=GRADE_NAME,
        generated_at=(generated_at or datetime.now(tz=UTC)).strftime("%Y-%m-%d %H:%MZ"),
        payload=Markup(json.dumps(index_payload(per_cluster, cost_shares))),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path
