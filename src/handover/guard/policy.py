"""Guard policy — what counts as a stall, how much a task may burn, what the
cage blocks. Layered: defaults < user file < machine (company) file < env path.

* user file:    ``~/.meerada/guard.toml``
* machine file: ``%ProgramData%\\Meerada\\guard.toml`` (Windows) or
                ``/etc/meerada/guard.toml`` — an IT department drops one file and
                every user on the machine runs under it; its ``locked`` list names
                the fields a user file may not override.
* ``MEERADA_GUARD_POLICY`` — explicit path, wins over both (for tests / pilots).
"""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

USER_FILE = Path.home() / ".meerada" / "guard.toml"


def machine_policy_path() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / "Meerada" / "guard.toml"
    return Path("/etc/meerada/guard.toml")


class Policy(BaseModel):
    """Everything the guard needs to decide. All money in USD."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    # --- stall / burn -------------------------------------------------------
    silence_s: float = 120.0  # no new output for this long = silent
    max_repeat: int = 3  # same tool + same args this many times = loop
    repeat_ratio: float = 0.6  # trigram overlap between recent answers = repeating
    session_budget_usd: float = 5.0  # hard cap per task/session (0 = off)
    daily_budget_usd: float = 25.0  # hard cap per day, all sessions (0 = off)
    burn_multiplier: float = 2.0  # spent > k x expected (from the exchange) = burning
    max_thinking_ratio: float = 8.0  # thinking tokens / output tokens above this = overthinking
    action: str = "alert"  # alert | stop  (stop = GuardedCaller refuses the next call)
    # --- cage ----------------------------------------------------------------
    cage: bool = True
    allowed_roots: tuple[str, ...] = ()  # workspace roots; empty = the current directory
    allowed_hosts: tuple[str, ...] = ()  # outbound hosts a model may reach; empty = warn on all
    block_secrets: bool = True  # secrets in outbound text -> block (else warn)
    cage_action: str = "warn"  # warn | block
    # --- company -------------------------------------------------------------
    webhook_url: str = ""  # Slack / Teams / Telegram-compatible JSON POST for every alert
    locked: tuple[str, ...] = ()  # fields the machine policy forbids users to change
    source: str = "defaults"  # where the effective policy came from (informational)

    def cap_hit(self, spent_session: float, spent_day: float) -> str:
        if self.session_budget_usd and spent_session >= self.session_budget_usd:
            return "session budget"
        if self.daily_budget_usd and spent_day >= self.daily_budget_usd:
            return "daily budget"
        return ""


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _tuples(d: dict[str, Any]) -> dict[str, Any]:
    return {k: tuple(v) if isinstance(v, list) else v for k, v in d.items()}


def load_policy(
    *,
    user_file: Path | None = None,
    machine_file: Path | None = None,
    env: dict[str, str] | None = None,
) -> Policy:
    """Merge the layers. A machine file's ``locked`` fields cannot be changed by
    the user file (company rules win); an explicit env path replaces everything."""
    src: Mapping[str, str] = os.environ if env is None else env
    explicit = src.get("MEERADA_GUARD_POLICY", "").strip()
    if explicit:
        data = _tuples(_read(Path(explicit)))
        return Policy(**{**data, "source": explicit})
    user = _tuples(_read(user_file if user_file is not None else USER_FILE))
    machine = _tuples(_read(machine_file if machine_file is not None else machine_policy_path()))
    locked = tuple(machine.get("locked", ()))
    merged = {k: v for k, v in user.items() if k not in locked}
    merged.update(machine)
    source = (
        "machine+user"
        if machine and user
        else "machine"
        if machine
        else "user"
        if user
        else "defaults"
    )
    merged.pop("source", None)
    return Policy(**merged, source=source)


def policy_text(policy: Policy) -> str:
    """Human summary for ``meerada guard policy``."""
    lines = [f"source: {policy.source}", f"enabled: {policy.enabled}"]
    lines.append(
        f"stall: silence {policy.silence_s:.0f}s · loop at {policy.max_repeat}x · "
        f"repeat ratio {policy.repeat_ratio} · thinking ratio {policy.max_thinking_ratio}"
    )
    lines.append(
        f"burn: session ${policy.session_budget_usd} · day ${policy.daily_budget_usd} · "
        f"{policy.burn_multiplier}x expected · action {policy.action}"
    )
    roots = ", ".join(policy.allowed_roots) or "(current directory)"
    hosts = ", ".join(policy.allowed_hosts) or "(warn on every outbound host)"
    lines.append(
        f"cage: {'on' if policy.cage else 'off'} · roots {roots} · hosts {hosts} · "
        f"secrets {'block' if policy.block_secrets else 'warn'} · action {policy.cage_action}"
    )
    if policy.webhook_url:
        lines.append("webhook: set")
    if policy.locked:
        lines.append("locked by company policy: " + ", ".join(policy.locked))
    return "\n".join(lines)
