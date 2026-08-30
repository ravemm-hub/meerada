"""Persist the continuous-grading state between ticks.

A single JSON file holds the GradeCards and the last-seen catalog versions, so
the loop survives across scheduled runs (cron / Task Scheduler). Metadata only.
"""

import json
from pathlib import Path

from handover.bench.continuous import ContinuousState, initial_state
from handover.bench.lifecycle import GradeCard


def load_state(path: Path) -> ContinuousState:
    if not path.exists():
        return initial_state()
    payload = json.loads(path.read_text(encoding="utf-8"))
    cards = {
        model_id: GradeCard.model_validate(card)
        for model_id, card in payload.get("cards", {}).items()
    }
    return ContinuousState(cards=cards, known_versions=dict(payload.get("known_versions", {})))


def save_state(path: Path, state: ContinuousState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cards": {mid: card.model_dump(mode="json") for mid, card in state.cards.items()},
        "known_versions": state.known_versions,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
