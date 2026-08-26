"""Reads raw events from a JSONL file (in-tenant) and yields normalized Traces."""

from collections.abc import Iterator
from pathlib import Path

from handover.collect.normalizer import Normalizer, RawEvent
from handover.schema.trace import Trace


def read_jsonl(path: Path, normalizer: Normalizer) -> Iterator[Trace]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            yield normalizer.normalize(RawEvent.model_validate_json(stripped))
