"""Per-user provider API keys for the hosted dashboard.

Each signed-in user pastes their own provider keys; the dashboard uses only that
user's keys to build that user's model callers. Keys are held in process memory,
never logged and never returned to the client (only the list of which providers
are connected). A production deployment would encrypt these at rest in a store;
this is the first hosted version's minimal, honest implementation.
"""


class KeyStore:
    def __init__(self) -> None:
        self._keys: dict[str, dict[str, str]] = {}

    def set(self, user: str, provider: str, key: str) -> None:
        key = key.strip()
        if not user or not provider or not key:
            return
        self._keys.setdefault(user, {})[provider] = key

    def get(self, user: str, provider: str) -> str | None:
        return self._keys.get(user, {}).get(provider) or None

    def providers(self, user: str) -> list[str]:
        return sorted(self._keys.get(user, {}))

    def clear(self, user: str, provider: str) -> None:
        self._keys.get(user, {}).pop(provider, None)
