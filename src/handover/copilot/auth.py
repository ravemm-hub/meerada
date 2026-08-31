"""Google sign-in and signed sessions for the hosted LLManager.

A real OAuth2 authorization-code flow: the browser is sent to Google, comes back
with a code, and we exchange it for the user's identity. The token exchange is
the only network seam (stdlib urllib) and is not unit-tested, like the model
HTTP client. Sessions are stateless HMAC-signed cookies — no session store.
Everything is driven by environment config; when it is absent the app runs open,
so local ``meerada up`` is unchanged.
"""

import base64
import hashlib
import hmac
import json
import os
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, ConfigDict

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SESSION_TTL_S = 7 * 24 * 3600
SESSION_COOKIE = "mrd_session"
STATE_COOKIE = "mrd_state"


class OAuthConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    session_secret: str = ""

    @property
    def configured(self) -> bool:
        return all(
            (self.client_id, self.client_secret, self.redirect_uri, self.session_secret)
        )


def config_from_env() -> OAuthConfig:
    return OAuthConfig(
        client_id=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        redirect_uri=os.environ.get("OAUTH_REDIRECT_URI", "").strip(),
        session_secret=os.environ.get("SESSION_SECRET", "").strip(),
    )


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, msg: bytes) -> str:
    return _b64u(hmac.new(secret.encode(), msg, hashlib.sha256).digest())


def sign_session(
    secret: str, claims: dict[str, Any], *, now: float, ttl_s: int = SESSION_TTL_S
) -> str:
    """A tamper-evident cookie value: base64(json).hmac."""
    payload = {**claims, "exp": int(now + ttl_s)}
    body = _b64u(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    return f"{body}.{_sign(secret, body.encode())}"


def verify_session(secret: str, token: str, *, now: float) -> dict[str, Any] | None:
    """Return the claims if the cookie is authentic and unexpired, else None."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(secret, body.encode())):
        return None
    try:
        claims = json.loads(_b64u_decode(body))
    except ValueError:
        return None
    if not isinstance(claims, dict) or float(claims.get("exp", 0)) < now:
        return None
    return claims


def new_state(secret: str) -> str:
    """A signed CSRF state token for the OAuth round-trip."""
    nonce = _b64u(os.urandom(12))
    return f"{nonce}.{_sign(secret, nonce.encode())}"


def check_state(secret: str, state: str) -> bool:
    if not state or "." not in state:
        return False
    nonce, sig = state.rsplit(".", 1)
    return hmac.compare_digest(sig, _sign(secret, nonce.encode()))


def login_url(cfg: OAuthConfig, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{query}"


class GoogleUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    sub: str
    email: str
    name: str


def exchange_code(cfg: OAuthConfig, code: str) -> GoogleUser:  # network seam; not unit-tested
    """Exchange the auth code for the signed-in Google user's identity."""
    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "redirect_uri": cfg.redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    token_req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST")
    with urllib.request.urlopen(token_req, timeout=15) as resp:
        token = json.loads(resp.read().decode())
    access = str(token.get("access_token", ""))
    info_req = urllib.request.Request(
        GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access}"}
    )
    with urllib.request.urlopen(info_req, timeout=15) as resp:
        info = json.loads(resp.read().decode())
    return GoogleUser(
        sub=str(info.get("sub", "")),
        email=str(info.get("email", "")),
        name=str(info.get("name") or info.get("email", "")),
    )
