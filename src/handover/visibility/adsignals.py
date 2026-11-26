"""Does this business pay for advertising? Read from its own public HTML.

A site that runs Google Ads carries a conversion tag (``AW-123456789`` in gtag), one that
runs Meta ads carries the Pixel (``fbq('init'``/``connect.facebook.net``), TikTok ads the
TikTok pixel, and most of them Google Tag Manager. These are facts the page publishes to
every visitor — no Google scraping, no third-party data. A business that pays for clicks
and is named in 0 of n AI answers is the lead the GEO machine is built around.
"""

from __future__ import annotations

import re

SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("google_ads", re.compile(r"\bAW-\d{6,}\b|googleadservices\.com|google_conversion_id", re.I)),
    (
        "meta_pixel",
        re.compile(r"connect\.facebook\.net/[^\"']*fbevents\.js|fbq\(\s*['\"]init", re.I),
    ),
    ("tiktok_pixel", re.compile(r"analytics\.tiktok\.com/i18n/pixel|ttq\.load\(", re.I)),
    ("gtm", re.compile(r"googletagmanager\.com/gtm\.js|\bGTM-[A-Z0-9]{4,}\b")),
)


def ad_signals(html: str) -> dict[str, bool]:
    """Which advertising tags the page carries, by name."""
    return {name: bool(rx.search(html)) for name, rx in SIGNALS}


def pays_for_ads(signals: dict[str, bool]) -> bool:
    """Paid acquisition is evidenced by an ads tag; GTM alone only says they measure."""
    return any(signals.get(k) for k in ("google_ads", "meta_pixel", "tiktok_pixel"))
