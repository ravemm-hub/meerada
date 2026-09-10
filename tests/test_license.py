"""Premium licensing: Lemon Squeezy verdicts are parsed, cached and gated — no network."""

import pytest

from handover.copilot import license as lic

GOOD = {"valid": True, "license_key": {"status": "active", "expires_at": "2027-09-01T00:00:00Z"},
        "meta": {"product_name": "Meerada LLManager Pro", "customer_email": "x@y.z"}}
DISABLED = {"valid": False, "error": "license_key not found", "license_key": {"status": "disabled"}}


def test_parse_status_reads_lemon_squeezy_shapes() -> None:
    s = lic.parse_status(GOOD, now=1.0)
    assert s.valid and s.product == "Meerada LLManager Pro" and s.expires_at.startswith("2027")
    bad = lic.parse_status(DISABLED, now=1.0)
    assert not bad.valid and "not found" in bad.reason
    assert not lic.parse_status({"valid": True, "license_key": {"status": "expired"}}, now=1).valid
    assert lic.parse_status({"activated": True, "license_key": {"status": "active"}}, now=1).valid


def test_check_caches_for_a_day_and_survives_outage() -> None:
    calls: list[str] = []

    def fetch(url: str, form: dict[str, str]) -> dict:
        calls.append(url)
        if len(calls) > 1:
            raise OSError("offline")
        return GOOD

    L = lic.Licenses(fetch, store="lemonsqueezy")
    assert L.check("KEY-1", now=100.0).valid and len(calls) == 1
    assert L.check("KEY-1", now=200.0).valid and len(calls) == 1  # cached
    assert L.check("KEY-1", now=100.0 + 86401).valid  # offline -> keep yesterday's good verdict
    assert not L.check("", now=1.0).valid
    def offline(u: str, f: dict[str, str]) -> dict:
        raise OSError("offline")

    fresh = lic.Licenses(offline, store="lemonsqueezy")
    assert "can't reach" in fresh.check("KEY-2").reason


def test_activate_falls_back_to_validate_when_instance_exists() -> None:
    seen: list[str] = []

    def fetch(url: str, form: dict[str, str]) -> dict:
        seen.append(url.rsplit("/", 1)[-1])
        if url == lic.ACTIVATE_URL:
            return {"activated": False, "error": "This license key has already been activated"}
        return GOOD

    s = lic.Licenses(fetch, store="lemonsqueezy").check("KEY-3", now=5.0, activate=True)
    assert s.valid and seen == ["activate", "validate"]


@pytest.mark.parametrize("feature,beta,licensed,ok", [
    ("send", False, False, True),      # free features always work
    ("judge", True, False, True),      # open beta: everything free
    ("judge", False, False, False),    # beta closed, no license
    ("judge", False, True, True),      # licensed
    ("attach_path", False, False, False),
])
def test_allowed_gate(feature: str, beta: bool, licensed: bool, ok: bool) -> None:
    assert lic.allowed(feature, licensed=licensed, beta=beta) is ok


GUMROAD_OK = {"success": True, "uses": 1, "purchase": {"product_name": "Meerada LLManager Pro",
              "email": "x@y.z", "refunded": False, "chargebacked": False, "license_key": "K"}}


def test_gumroad_verify_shapes_and_activation_counting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEERADA_LICENSE_PROVIDER", "gumroad")
    monkeypatch.setenv("MEERADA_GUMROAD_PRODUCT_ID", "prod_123")
    seen: list[dict] = []

    def fetch(url: str, form: dict[str, str]) -> dict:
        seen.append(form)
        assert url == lic.GUMROAD_VERIFY_URL and form["product_id"] == "prod_123"
        return GUMROAD_OK

    L = lic.Licenses(fetch)
    assert L.check("K", now=1.0, activate=True).valid and seen[-1]["increment_uses_count"] == "true"
    L2 = lic.Licenses(fetch)
    assert L2.check("K", now=2.0).product == "Meerada LLManager Pro"
    assert seen[-1]["increment_uses_count"] == "false"  # plain checks never burn a use
    missing = {"success": False, "message": "That license does not exist"}
    assert not lic.parse_gumroad(missing, now=1).valid
    refunded = {"success": True, "purchase": {"refunded": True}}
    assert "refunded" in lic.parse_gumroad(refunded, now=1).reason
    ended = {"success": True, "purchase": {"subscription_ended_at": "2027-01-01"}}
    assert not lic.parse_gumroad(ended, now=1).valid


def test_beta_open_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEERADA_BETA_OPEN", raising=False)
    assert lic.beta_open()
    monkeypatch.setenv("MEERADA_BETA_OPEN", "0")
    assert not lic.beta_open()
