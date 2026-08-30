"""Live model-catalog fetch for the continuous loop.

Queries an OpenAI-compatible ``/models`` endpoint (OpenAI, Groq, OpenRouter,
DeepSeek, Mistral, Together) and returns the models on offer as CatalogModels,
tagged with the provider's own version/created hint so a silent upgrade shows
up as a version change. The HTTP call is the only seam; tests inject a fake.
Pure metadata — model ids and version hints only.
"""

import json
import urllib.request
from collections.abc import Callable, Sequence

from handover.bench.discovery import CatalogModel
from handover.replay.openai_client import ENDPOINTS

# Raw fetch: returns the parsed JSON body of GET {base}/models.
RawModelsFetch = Callable[[str, str], dict]


def _urllib_fetch(base_url: str, api_key: str) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "meerada/0.1"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as resp:
        result: dict = json.loads(resp.read().decode())
        return result


def parse_models(provider: str, body: dict) -> list[CatalogModel]:
    """Normalize an OpenAI-compatible /models body to CatalogModels."""
    models: list[CatalogModel] = []
    for item in body.get("data", []):
        model_id = str(item.get("id") or "").strip()
        if not model_id:
            continue
        # version hint: prefer an explicit created/updated stamp so a silent
        # re-release under the same id is detected as an upgrade.
        version = str(
            item.get("created") or item.get("updated_at") or item.get("version") or "unknown"
        )
        models.append(CatalogModel(provider=provider, model_id=model_id, version_hint=version))
    return models


def fetch_catalog(
    providers: Sequence[str],
    api_keys: dict[str, str],
    *,
    raw_fetch: RawModelsFetch = _urllib_fetch,
) -> list[CatalogModel]:
    """Fetch and merge catalogs across the providers we hold a key for.

    A provider that errors or has no key is skipped (never fails the whole
    tick) — the loop grades whatever it can reach.
    """
    out: list[CatalogModel] = []
    for provider in providers:
        key = api_keys.get(provider, "").strip()
        base = ENDPOINTS.get(provider)
        if not key or not base:
            continue
        try:
            body = raw_fetch(base, key)
        except Exception:
            continue
        out.extend(parse_models(provider, body))
    return out
