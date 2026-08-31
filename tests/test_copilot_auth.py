"""Auth: signed sessions, CSRF state, login URL, key store.
The Google token exchange is a network seam and is not exercised here (CLAUDE.md)."""

from handover.copilot.auth import (
    OAuthConfig,
    check_state,
    login_url,
    new_state,
    sign_session,
    verify_session,
)
from handover.copilot.keystore import KeyStore

SECRET = "test-secret-please-change"


def test_session_round_trip() -> None:
    token = sign_session(SECRET, {"sub": "u1", "email": "a@b.com"}, now=1000.0)
    claims = verify_session(SECRET, token, now=1000.0)
    assert claims is not None
    assert claims["sub"] == "u1" and claims["email"] == "a@b.com"


def test_session_tamper_is_rejected() -> None:
    token = sign_session(SECRET, {"sub": "u1"}, now=1000.0)
    body, sig = token.rsplit(".", 1)
    forged = f"{body}x.{sig}"
    assert verify_session(SECRET, forged, now=1000.0) is None
    assert verify_session("other-secret", token, now=1000.0) is None


def test_session_expiry() -> None:
    token = sign_session(SECRET, {"sub": "u1"}, now=1000.0, ttl_s=60)
    assert verify_session(SECRET, token, now=1000.0 + 30) is not None
    assert verify_session(SECRET, token, now=1000.0 + 120) is None


def test_session_garbage_is_rejected() -> None:
    assert verify_session(SECRET, "", now=1.0) is None
    assert verify_session(SECRET, "nodot", now=1.0) is None
    assert verify_session(SECRET, "a.b.c", now=1.0) is None


def test_state_round_trip_and_tamper() -> None:
    state = new_state(SECRET)
    assert check_state(SECRET, state) is True
    assert check_state(SECRET, state + "x") is False
    assert check_state(SECRET, "nope") is False


def test_login_url_carries_params() -> None:
    cfg = OAuthConfig(
        client_id="cid", client_secret="sec", redirect_uri="https://x/cb", session_secret=SECRET
    )
    url = login_url(cfg, "state123")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=cid" in url and "state=state123" in url and "scope=openid" in url


def test_config_configured_flag() -> None:
    assert OAuthConfig().configured is False
    assert (
        OAuthConfig(
            client_id="a", client_secret="b", redirect_uri="c", session_secret="d"
        ).configured
        is True
    )


def test_keystore() -> None:
    ks = KeyStore()
    ks.set("u1", "groq", "  gsk_abc  ")
    assert ks.get("u1", "groq") == "gsk_abc"
    assert ks.get("u1", "openai") is None
    assert ks.get("u2", "groq") is None
    ks.set("u1", "openai", "sk_xyz")
    assert ks.providers("u1") == ["groq", "openai"]
    ks.set("u1", "groq", "   ")  # blank ignored
    assert ks.get("u1", "groq") == "gsk_abc"
    ks.clear("u1", "groq")
    assert ks.get("u1", "groq") is None
