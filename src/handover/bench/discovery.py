"""Model discovery — detect new and upgraded models the moment they appear.

Polls a provider catalog (the fetch is an injected seam, faked in tests) and
diffs it against what we already grade. A newly-appeared model, or one whose
version fingerprint changed (a silent upgrade), is flagged for immediate
provisional grading — that is how the index stays near-real-time.

Pure metadata: model ids and version hints only.
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

Change = Literal["new", "upgraded", "removed"]


class CatalogModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model_id: str
    version_hint: str = "unknown"  # provider snapshot / build id, when exposed


class ModelChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    model_id: str
    change: Change
    previous_version: str | None = None
    current_version: str | None = None

    @property
    def needs_grading(self) -> bool:
        """A new or upgraded model needs a fresh (provisional) grade now."""
        return self.change in ("new", "upgraded")


def diff_catalog(current: Sequence[CatalogModel], known: Mapping[str, str]) -> list[ModelChange]:
    """Compare a freshly-fetched catalog to the versions we last graded.

    ``known`` maps model_id -> the version_hint we last saw. Returns the
    changes, new/upgraded first (they need grading), removed last.
    """
    changes: list[ModelChange] = []
    seen: set[str] = set()

    for model in current:
        seen.add(model.model_id)
        if model.model_id not in known:
            changes.append(
                ModelChange(
                    provider=model.provider,
                    model_id=model.model_id,
                    change="new",
                    current_version=model.version_hint,
                )
            )
        elif known[model.model_id] != model.version_hint:
            changes.append(
                ModelChange(
                    provider=model.provider,
                    model_id=model.model_id,
                    change="upgraded",
                    previous_version=known[model.model_id],
                    current_version=model.version_hint,
                )
            )

    for model_id, version in known.items():
        if model_id not in seen:
            provider = next((m.provider for m in current if m.model_id == model_id), "unknown")
            changes.append(
                ModelChange(
                    provider=provider,
                    model_id=model_id,
                    change="removed",
                    previous_version=version,
                )
            )

    order = {"new": 0, "upgraded": 1, "removed": 2}
    changes.sort(key=lambda c: (order[c.change], c.model_id))
    return changes


def to_grade(changes: Sequence[ModelChange]) -> list[str]:
    """Model ids that need a fresh grade now (new + upgraded)."""
    return [c.model_id for c in changes if c.needs_grading]
