"""The cage — is the model trying to take something out of the workspace?

Inspects *outbound* text (prompts, tool-call arguments, shell commands) before
it leaves the machine or runs. Findings never contain the secret itself: the
snippet is redacted to a prefix. Pure functions; the policy decides warn/block.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal
from urllib.parse import urlparse

from handover.guard.policy import Policy

Kind = Literal["secret", "outside_workspace", "network", "env_dump"]
Severity = Literal["warn", "block"]

_SECRETS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("OpenAI key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("Slack token", re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "generic api key",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+]{16,})"
        ),
    ),
)
_NET_CMD = re.compile(
    r"(?i)(?<![\w.\-/\\])(curl|wget|scp|rsync|sftp|ssh|nc|ncat|netcat|Invoke-WebRequest|Invoke-RestMethod|"
    r"iwr|irm|Start-BitsTransfer|aws s3 (?:cp|sync)|gsutil cp|gh release upload|git push)\b"
)
_URL = re.compile(r"https?://[^\s'\"<>)]+")
_ENV_DUMP = re.compile(
    r"(?i)(?<![\w-])(printenv|env\b(?!\w)|set\b(?=\s*$)|Get-ChildItem Env:|\$env:|"
    r"cat\s+~?/?\.?(?:ssh|aws|gnupg|kube)/|\.env\b|~/\.netrc|id_rsa|credentials\.json|\.npmrc|\.pypirc)"
)
_PATH = re.compile(
    r"(?:[A-Za-z]:\\[^\s'\"<>|*?]+|(?<![\w./-])/(?:home|Users|root|etc|var|opt|mnt|srv|tmp)/[^\s'\"<>|*?]*)"
)
_HOSTS_ALWAYS_OK = ("localhost", "127.0.0.1", "::1")


@dataclass(frozen=True)
class Finding:
    kind: Kind
    severity: Severity
    what: str  # human label, never the secret
    snippet: str  # redacted

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "what": self.what,
            "snippet": self.snippet,
        }


def redact(s: str, keep: int = 4) -> str:
    s = s.strip()
    return s[:keep] + "…" + "*" * min(8, max(0, len(s) - keep)) if len(s) > keep else "****"


def scrub(s: str) -> str:
    """Replace any secret inside ``s`` with its redacted form — snippets of
    commands and paths must never carry the key they sit next to."""
    for _label, rx in _SECRETS:
        s = rx.sub(lambda m: redact(m.group(1) if m.groups() else m.group(0)), s)
    return s


def _under(path: str, roots: tuple[Path, ...]) -> bool:
    p: object = PureWindowsPath(path) if re.match(r"^[A-Za-z]:\\", path) else PurePosixPath(path)
    ps = str(p).replace("\\", "/").lower().rstrip("/")
    for r in roots:
        rs = str(r).replace("\\", "/").lower().rstrip("/")
        if ps == rs or ps.startswith(rs + "/"):
            return True
    return False


def workspace_roots(policy: Policy, cwd: Path | None = None) -> tuple[Path, ...]:
    roots = tuple(Path(r).expanduser() for r in policy.allowed_roots) or (cwd or Path.cwd(),)
    tmp = Path.home() / "AppData" / "Local" / "Temp"
    return (*roots, tmp, Path("/tmp"))


def inspect_outbound(text: str, policy: Policy, *, cwd: Path | None = None) -> list[Finding]:
    """Every cage finding in ``text``. Empty list = nothing to worry about."""
    if not policy.cage or not text:
        return []
    out: list[Finding] = []
    sev_secret: Severity = "block" if policy.block_secrets else "warn"
    for label, rx in _SECRETS:
        for m in rx.finditer(text):
            token = m.group(1) if m.groups() else m.group(0)
            out.append(Finding("secret", sev_secret, label, redact(token)))
    sev: Severity = "block" if policy.cage_action == "block" else "warn"
    roots = workspace_roots(policy, cwd)
    for m in _PATH.finditer(text):
        path = m.group(0).rstrip(".,;:")
        if not _under(path, roots):
            out.append(
                Finding("outside_workspace", sev, "path outside the workspace", scrub(path[:80]))
            )
    for m in _NET_CMD.finditer(text):
        out.append(
            Finding(
                "network",
                sev,
                f"outbound command: {m.group(1)}",
                scrub(text[m.start() : m.start() + 60].strip()),
            )
        )
    for m in _URL.finditer(text):
        host = (urlparse(m.group(0)).hostname or "").lower()
        if host in _HOSTS_ALWAYS_OK or not host:
            continue
        if policy.allowed_hosts and any(
            host == h or host.endswith("." + h) for h in policy.allowed_hosts
        ):
            continue
        if not policy.allowed_hosts and not _NET_CMD.search(text):
            continue  # a bare link in prose is not an exfil attempt; a link in a curl is
        out.append(Finding("network", sev, f"outbound host: {host}", host))
    for m in _ENV_DUMP.finditer(text):
        out.append(
            Finding("env_dump", sev, "reads secrets from the environment / dotfiles", m.group(1))
        )
    seen: set[tuple[str, str]] = set()
    uniq: list[Finding] = []
    for f in out:
        key = (f.kind, f.snippet)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def decision(findings: list[Finding]) -> Literal["allow", "warn", "block"]:
    if any(f.severity == "block" for f in findings):
        return "block"
    return "warn" if findings else "allow"
