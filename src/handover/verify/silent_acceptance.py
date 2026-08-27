"""Grade B (derived): downstream acceptance — the diff was approved, or there was
no retry within 10 minutes and no correction message (SPEC §5.1)."""

from typing import Literal

from handover.schema.task import Task
from handover.schema.trace import Verification
from handover.verify.base import Artifacts, Verdict


class SilentAcceptanceVerifier:
    name = "silent_acceptance"
    grade: Literal["measured", "derived"] = "derived"

    def applies_to(self, task: Task, artifacts: Artifacts) -> bool:
        return artifacts.accepted_downstream is not None or artifacts.retried_within_10m is not None

    def verify(self, task: Task, artifacts: Artifacts) -> Verdict:
        if artifacts.accepted_downstream:
            passed, confidence = True, 1.0
        else:
            rejected = bool(artifacts.retried_within_10m) or bool(artifacts.correction_followed)
            passed, confidence = not rejected, 0.7
        return Verification(
            status="pass" if passed else "fail",
            method="downstream",
            signal="silent_acceptance",
            confidence=confidence,
            evidence_grade="derived",
        )
