"""Premium licensing — Lemon Squeezy license keys, validated at the source.

The desktop app stays free during the open beta (``MEERADA_BETA_OPEN`` unset or
"1"); when the beta closes, the free tier keeps 5 live sessions and 5 model
switches a month, and Pro ($99/year, one payment) unlocks unlimited sessions and
switches plus judge, relay, fork and attachments — a license key bought through
Lemon Squeezy. Keys are
validated against Lemon Squeezy's public license API (no secret needed on our
side), cached for a day, and stored encrypted in the user's key vault like any
other key. The HTTP call is the only seam; tests inject a fake.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

VALIDATE_URL = "https://api.lemonsqueezy.com/v1/licenses/validate"
ACTIVATE_URL = "https://api.lemonsqueezy.com/v1/licenses/activate"
# Gumroad's license API (product_id + license_key; increments use count unless told not to).
GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"


def provider() -> str:
    """Which store issues our keys: 'gumroad' (default) or 'lemonsqueezy'."""
    return os.environ.get("MEERADA_LICENSE_PROVIDER", "gumroad").strip().lower()


def gumroad_product_id() -> str:
    return os.environ.get("MEERADA_GUMROAD_PRODUCT_ID", "").strip()
CACHE_TTL_S = 86400
PREMIUM_FEATURES = frozenset(
    {"judge", "relay", "fork", "attach", "attach_path", "sessions", "switch"}
)
FREE_SESSIONS = 5  # live sessions on the free tier
FREE_SWITCHES_PER_MONTH = 5  # free-tier model switches per month
PRO_PRICE_USD_YEAR = 99
LicenseFetch = Callable[[str, dict[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class LicenseStatus:
    valid: bool
    reason: str = ""  # human text when not valid
    product: str = ""
    customer: str = ""
    expires_at: str = ""
    checked_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid, "reason": self.reason, "product": self.product,
            "customer": self.customer, "expires_at": self.expires_at,
        }


def _post(url: str, form: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Accept": "application/json", "User-Agent": "meerada/0.2"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body: dict[str, Any] = json.loads(resp.read().decode())
            return body
    except urllib.error.HTTPError as exc:  # LS answers 4xx with a JSON body too
        try:
            body = json.loads(exc.read().decode())
            return body if isinstance(body, dict) else {"error": str(exc)}
        except ValueError:
            return {"error": f"HTTP {exc.code}"}


def parse_gumroad(body: dict[str, Any], *, now: float) -> LicenseStatus:
    """Normalise a Gumroad /licenses/verify response. A refunded, disputed or
    subscription-ended purchase is not a valid license."""
    if not isinstance(body, dict):
        return LicenseStatus(False, "unreadable response", checked_at=now)
    p = body.get("purchase") or {}
    if not body.get("success"):
        return LicenseStatus(False, str(body.get("message") or "invalid key"), checked_at=now)
    dead = p.get("refunded") or p.get("chargebacked") or p.get("disputed")
    ended = p.get("subscription_ended_at") or p.get("subscription_cancelled_at")
    if dead or ended:
        return LicenseStatus(False, "license refunded or ended", checked_at=now)
    return LicenseStatus(
        True, "", product=str(p.get("product_name") or ""),
        customer=str(p.get("email") or ""), expires_at="", checked_at=now,
    )


def parse_status(body: dict[str, Any], *, now: float) -> LicenseStatus:
    """Normalise a Lemon Squeezy validate/activate response."""
    if not isinstance(body, dict):
        return LicenseStatus(False, "unreadable response", checked_at=now)
    lic = body.get("license_key") or {}
    meta = body.get("meta") or {}
    status = str(lic.get("status") or "")
    ok = bool(body.get("valid") or body.get("activated")) and status in ("active", "")
    if not ok:
        reason = str(body.get("error") or (f"license {status}" if status else "invalid key"))
        return LicenseStatus(False, reason, checked_at=now)
    return LicenseStatus(
        True, "", product=str(meta.get("product_name") or ""),
        customer=str(meta.get("customer_email") or ""),
        expires_at=str(lic.get("expires_at") or ""), checked_at=now,
    )


class Licenses:
    """Validate + cache license keys; ``fetch`` is injectable for tests."""

    def __init__(
        self,
        fetch: LicenseFetch = _post,
        instance: str = "meerada-desktop",
        store: str | None = None,
    ) -> None:
        self._fetch = fetch
        self._instance = instance
        self._store = store  # None -> MEERADA_LICENSE_PROVIDER at call time
        self._cache: dict[str, LicenseStatus] = {}

    def check(self, key: str, *, now: float | None = None, activate: bool = False) -> LicenseStatus:
        now = time.time() if now is None else now
        key = (key or "").strip()
        if not key:
            return LicenseStatus(False, "no license key", checked_at=now)
        cached = self._cache.get(key)
        if cached and now - cached.checked_at < CACHE_TTL_S and not activate:
            return cached
        gumroad = (self._store or provider()) == "gumroad"
        if gumroad:
            # a plain re-check must not burn an activation: increment only on activate
            form = {
                "product_id": gumroad_product_id(), "license_key": key,
                "increment_uses_count": "true" if activate else "false",
            }
            url = GUMROAD_VERIFY_URL
        else:
            form = {"license_key": key, "instance_name": self._instance}
            url = ACTIVATE_URL if activate else VALIDATE_URL
        try:
            body = self._fetch(url, form)
        except Exception as exc:
            # offline: keep a previously-good verdict for the day rather than lock the user out
            if cached and cached.valid:
                return cached
            why = f"can't reach the license server ({type(exc).__name__})"
            return LicenseStatus(False, why, checked_at=now)
        status = parse_gumroad(body, now=now) if gumroad else parse_status(body, now=now)
        if not gumroad and activate and not status.valid and "already" in status.reason.lower():
            status = self.check(key, now=now)  # instance already activated: plain validate
        self._cache[key] = status
        return status


def beta_open() -> bool:
    """Open beta: every feature free. Flip with MEERADA_BETA_OPEN=0 when pricing goes live."""
    return os.environ.get("MEERADA_BETA_OPEN", "1") != "0"


def allowed(feature: str, *, licensed: bool, beta: bool) -> bool:
    """Is ``feature`` usable right now? Free features always; premium ones need
    the beta to be open or a valid license."""
    return feature not in PREMIUM_FEATURES or beta or licensed
