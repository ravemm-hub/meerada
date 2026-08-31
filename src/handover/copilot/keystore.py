"""Per-user provider API keys — encrypted at rest, persisted across restarts.

Each signed-in user connects their own provider keys; the dashboard uses only
that user's keys to build that user's model callers. Keys are encrypted with
Fernet (AES-128-CBC + HMAC) under a key derived from a secret via scrypt, and
written to a JSON file so they survive restarts. When ``cryptography`` is not
installed the store still works and persists, but warns that keys are stored
unencrypted — install the ``hosted`` extra to enable encryption. Keys are never
logged and never returned to the client (only which providers are connected).
"""

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

_SCRYPT_SALT = b"meerada-keyvault-v1"


def _fernet(secret: str) -> Any:
    """A Fernet cipher derived from ``secret``, or None if unavailable."""
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    key = hashlib.scrypt(secret.encode(), salt=_SCRYPT_SALT, n=2**14, r=8, p=1, dklen=32)
    return Fernet(base64.urlsafe_b64encode(key))


class KeyStore:
    def __init__(self, *, path: str | None = None, secret: str = "") -> None:
        self._path = Path(path) if path else None
        self._cipher = _fernet(secret)
        self._keys: dict[str, dict[str, str]] = {}
        if self._path is not None and secret and self._cipher is None:
            print(
                "WARNING: a keyvault secret is set but 'cryptography' is missing — "
                "keys are stored UNENCRYPTED. Install the hosted extra: pip install '.[hosted]'"
            )
        self._load()

    @property
    def encrypted(self) -> bool:
        return self._cipher is not None

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        raw = self._path.read_bytes()
        if not raw:
            return
        try:
            if self._cipher is not None:
                raw = self._cipher.decrypt(raw)
            loaded = json.loads(raw.decode())
            if isinstance(loaded, dict):
                self._keys = {
                    str(u): {str(p): str(k) for p, k in v.items()} for u, v in loaded.items()
                }
        except Exception:  # unreadable, tampered, or wrong secret -> start clean
            self._keys = {}

    def _save(self) -> None:
        if self._path is None:
            return
        blob = json.dumps(self._keys, separators=(",", ":")).encode()
        if self._cipher is not None:
            blob = self._cipher.encrypt(blob)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(blob)

    def set(self, user: str, provider: str, key: str) -> None:
        key = key.strip()
        if not user or not provider or not key:
            return
        self._keys.setdefault(user, {})[provider] = key
        self._save()

    def get(self, user: str, provider: str) -> str | None:
        return self._keys.get(user, {}).get(provider) or None

    def providers(self, user: str) -> list[str]:
        return sorted(self._keys.get(user, {}))

    def clear(self, user: str, provider: str) -> None:
        self._keys.get(user, {}).pop(provider, None)
        self._save()
