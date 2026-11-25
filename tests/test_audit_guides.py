"""T3: the entity audit (fake fetch) and the guide generator."""

from __future__ import annotations

from pathlib import Path

from handover.visibility.audit import audit, format_audit, robots_blocks
from handover.visibility.guides import Business, Guide, build_guides, render_guide

HOME = (
    """<!doctype html><html lang="he"><head><title>Test Plumbing — plumber in Tel Aviv</title>
<script type="application/ld+json">{"@type":"LocalBusiness"}</script></head>
<body><h1>Test Plumbing</h1><p>Emergency plumber in Tel Aviv, open 24/7. Hours: Sun-Thu 08:00-20:00.
Call 03-555-1234. Address: 12 Dizengoff Street, Tel Aviv. Leak repair from ₪350. Updated 2026.</p>
<a href="https://instagram.com/testplumb">ig</a> <a href="https://facebook.com/testplumb">fb</a>
"""
    + ("<p>word </p>" * 320)
    + "</body></html>"
)

ROBOTS_BLOCKING = "User-agent: *\nDisallow: /\n\nUser-agent: Googlebot\nAllow: /\n"


def _fetch(pages: dict[str, tuple[int, str]]):  # type: ignore[no-untyped-def]
    def fetch(url: str) -> tuple[int, dict[str, str], str]:
        for suffix, (status, body) in pages.items():
            if url.endswith(suffix):
                return status, {}, body
        return 404, {}, ""

    return fetch


def test_robots_parser_honours_specific_groups_and_wildcard() -> None:
    blocks = robots_blocks(ROBOTS_BLOCKING, ("OAI-SearchBot", "Googlebot"))
    assert blocks == {"OAI-SearchBot": True, "Googlebot": False}
    assert robots_blocks("", ("PerplexityBot",)) == {"PerplexityBot": False}


def test_audit_scores_a_good_site_and_lists_fixes_for_a_bad_one() -> None:
    good = audit(
        "test-plumb.co.il",
        "Test Plumbing",
        _fetch(
            {
                "test-plumb.co.il": (200, HOME),
                "/robots.txt": (200, "User-agent: *\nAllow: /\n"),
                "/sitemap.xml": (200, "<urlset/>"),
            }
        ),
    )
    assert good.url.startswith("https://") and good.score >= 85
    keys = {c.key: c.ok for c in good.checks}
    assert (
        keys["search_bots"]
        and keys["phone"]
        and keys["address"]
        and keys["prices"]
        and keys["social"]
    )
    assert good.as_dict()["grade"] == "declared"

    bad = audit(
        "https://blocked.example",
        "Blocked Co",
        _fetch(
            {
                "blocked.example": (200, "<html><body><img src=x></body></html>"),
                "/robots.txt": (200, ROBOTS_BLOCKING),
            }
        ),
    )
    assert bad.score < 30
    assert bad.fixes()[0].startswith("Unblock the search crawlers") or bad.fixes()[0].startswith(
        "Fix the site"
    )
    assert "Unblock the search crawlers" in format_audit(bad)


def test_guide_renders_alphabetically_with_disclosure_and_jsonld(tmp_path: Path) -> None:
    g = Guide(
        slug="tel-aviv-plumbers",
        city="Tel Aviv",
        country="Israel",
        category="plumber",
        title="Plumbers in Tel Aviv compared by hours, areas and prices",
        intro="Twelve plumbers, the facts.",
        criteria=["24/7 availability", "areas served", "published prices"],
        updated="2026-11-26",
        businesses=[
            Business(
                name="Zeta Pipes",
                website="https://zeta.example",
                hours="24/7",
                prices="from ₪350",
                source="https://zeta.example",
                checked="2026-11-26",
                note="Licensed since 2010.",
            ),
            Business(name="Alpha Plumbing", website="https://alpha.example", phone="03-5551234"),
        ],
        sources=["https://zeta.example", "https://alpha.example"],
    )
    html = render_guide(g)
    assert html.index("Alpha Plumbing") < html.index("Zeta Pipes")
    assert "did not pay and were not consulted" in html and "application/ld+json" in html
    assert '"@type": "ItemList"' in html and "star" not in html.lower()
    data = tmp_path / "guides"
    data.mkdir()
    (data / "tel-aviv-plumbers.json").write_text(g.model_dump_json(), encoding="utf-8")
    written = build_guides(data, tmp_path / "out")
    assert [p.name for p in written] == ["tel-aviv-plumbers.html", "index.html"]
    assert "Guides" in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
