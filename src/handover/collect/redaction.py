"""Active egress guard (defense in depth for CLAUDE.md rule 1).

The Trace schema already forbids content structurally. This module is the
second wall: before any bundle leaves the tenant boundary, scan its serialized
form for shapes that look like leaked content and refuse to emit if found.

The guard is deliberately conservative — it inspects only for high-signal leak
markers (long free-text runs in fields that should be metadata, values that
match known content) and never sees the tenant salt.
"""

import json
import re
from typing import Any

# A metadata field is short and structured. These caps flag anything that
# smells like prose or a raw payload smuggled into a metadata channel.
MAX_LABEL_CHARS = 60
MAX_SIGNAL_CHARS = 64
MAX_ID_CHARS = 40  # every real model id / tool name fits; multi-word content does not
MAX_ID_SEGMENTS = 7
MAX_GENERIC_STRING_CHARS = 256

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_REF = re.compile(r"^(trace|template)://")
# Fields whose values are free-form but must stay label-sized.
_LABEL_KEYS = {"label", "cluster_label", "note", "signal", "verifier_spec"}


class ContentLeakError(RuntimeError):
    """Raised when an about-to-leave bundle contains suspected content."""


def _looks_like_prose(value: str) -> bool:
    """Heuristic: several words with sentence-like spacing = probably content."""
    return len(value.split()) > 8 and value.count(" ") > 6


def scan_value(key: str, value: Any, path: str, findings: list[str]) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            scan_value(str(k), v, f"{path}.{k}", findings)
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            scan_value(key, v, f"{path}[{i}]", findings)
        return
    if not isinstance(value, str):
        return

    # Pointers and fingerprints are always safe, any length.
    if _FINGERPRINT.match(value) or _REF.match(value):
        return

    if key in _LABEL_KEYS:
        cap = MAX_SIGNAL_CHARS if key in {"signal", "verifier_spec"} else MAX_LABEL_CHARS
        if len(value) > cap or _looks_like_prose(value):
            findings.append(f"{path}: {key} exceeds label size ({len(value)} chars)")
        return

    if key in {"model_id", "from_model", "to_model", "provider", "model_version_hint"}:
        # A real identifier is short with few segments (claude-haiku-4-5-2025...).
        # Many words/segments, whitespace, or length is content, not an id.
        segments = len(re.split(r"[-_./: ]+", value.strip()))
        if len(value) > MAX_ID_CHARS or segments > MAX_ID_SEGMENTS or " " in value.strip():
            findings.append(f"{path}: {key} looks like content, not an identifier")
        return

    # Any other free string that is prose-shaped is suspicious in an export.
    if len(value) > MAX_GENERIC_STRING_CHARS or _looks_like_prose(value):
        findings.append(f"{path}: free-text value of {len(value)} chars may be content")


def assert_metadata_only(bundle: Any, *, name: str = "bundle") -> None:
    """Raise ContentLeakError if the serializable bundle looks like it carries
    content. Call this on anything crossing the tenant boundary."""
    payload = json.loads(json.dumps(bundle, default=str))
    findings: list[str] = []
    scan_value(name, payload, name, findings)
    if findings:
        raise ContentLeakError(
            f"{name} blocked from export — suspected content leak:\n  " + "\n  ".join(findings)
        )


def is_metadata_only(bundle: Any) -> bool:
    try:
        assert_metadata_only(bundle)
    except ContentLeakError:
        return False
    return True
