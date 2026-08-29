"""Output-equivalence verification — the quality guarantee for migration.

The migration promise is "as good as the model you're leaving," not merely
"well-formed." This verifier compares a candidate output to the incumbent's
proven-good output (grade A: measured):

- JSON: field-level equality on the keys the incumbent produced. Extra keys are
  tolerated; a missing or changed required value is a quality regression.
- Numbers embedded in text: the set of numbers must match (catches an extraction
  that kept the shape but changed the value — the classic silent regression).
- Code: the candidate must pass the SAME tests the incumbent passed
  (candidate_exit_code == 0), never a text diff.
- Plain text: normalized-exact by default (strict), because a loose text match
  would let quality drift through. Fuzzy/semantic matching is the jury's job
  (grade C), never smuggled in here as if it were measured.

Everything runs in-tenant; only pass/fail leaves.
"""

import json
import re
from typing import Any, Literal

from handover.schema.task import Task
from handover.schema.trace import Verification
from handover.verify.base import Artifacts, Verdict

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class EquivalenceVerifier:
    name = "output_equivalence"
    grade: Literal["measured", "derived"] = "measured"

    def applies_to(self, task: Task, artifacts: Artifacts) -> bool:
        return artifacts.expected_output is not None and artifacts.output_text is not None

    def verify(self, task: Task, artifacts: Artifacts) -> Verdict:
        assert artifacts.expected_output is not None and artifacts.output_text is not None
        passed, signal = self._compare(
            artifacts.expected_output, artifacts.output_text, artifacts.candidate_exit_code
        )
        return Verification(
            status="pass" if passed else "fail",
            method="programmatic",
            signal=signal,
            confidence=1.0,
            evidence_grade="measured",
        )

    def _compare(
        self, expected: str, candidate: str, candidate_exit_code: int | None
    ) -> tuple[bool, str]:
        # Code path: the candidate must pass the same tests, not look similar.
        if candidate_exit_code is not None:
            return candidate_exit_code == 0, "equiv_test_pass"

        exp_json = _try_json(expected)
        cand_json = _try_json(candidate)
        if exp_json is not None:
            if cand_json is None:
                return False, "equiv_json_unparseable"
            return _json_superset(exp_json, cand_json), "equiv_json_fields"

        # Non-JSON: numbers must match (guards silent value drift), then text.
        exp_nums, cand_nums = _NUMBER.findall(expected), _NUMBER.findall(candidate)
        if exp_nums and sorted(exp_nums) != sorted(cand_nums):
            return False, "equiv_number_mismatch"

        return _normalize(expected) == _normalize(candidate), "equiv_text_exact"


def _try_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _json_superset(expected: Any, candidate: Any) -> bool:
    """Every key/value the incumbent produced must be present and equal in the
    candidate. Extra candidate keys are allowed; missing or changed ones fail."""
    if isinstance(expected, dict):
        if not isinstance(candidate, dict):
            return False
        return all(k in candidate and _json_superset(v, candidate[k]) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(candidate, list) or len(expected) != len(candidate):
            return False
        return all(_json_superset(a, b) for a, b in zip(expected, candidate, strict=True))
    if isinstance(expected, float) or isinstance(candidate, float):
        try:
            return abs(float(expected) - float(candidate)) < 1e-9
        except (TypeError, ValueError):
            return bool(expected == candidate)
    return bool(expected == candidate)


def _normalize(text: str) -> str:
    return " ".join(text.split()).strip().lower()
