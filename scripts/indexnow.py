"""Tell Bing (and every IndexNow partner) that pages on meerada.app changed.

    python scripts/indexnow.py https://meerada.app/guides/tel-aviv-plumbers.html ...

The key lives in data/indexnow-key.txt and is served at https://meerada.app/<key>.txt
(the file sits in site/ and on gh-pages). ChatGPT search is Bing-backed, so this is the
fastest sanctioned way to get a new page into its index.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

HOST = "meerada.app"


def main(urls: list[str]) -> int:
    key = Path(__file__).resolve().parent.parent.joinpath("data/indexnow-key.txt").read_text().strip()
    body = {
        "host": HOST,
        "key": key,
        "keyLocation": f"https://{HOST}/{key}.txt",
        "urlList": urls,
    }
    req = urllib.request.Request(
        "https://api.indexnow.org/IndexNow",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(f"IndexNow: HTTP {resp.status} for {len(urls)} url(s)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: indexnow.py <url> [url ...]")
    raise SystemExit(main(sys.argv[1:]))
