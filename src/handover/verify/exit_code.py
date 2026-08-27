"""Grade A: a recorded process exit code (tests, compiler, script)."""

from typing import Literal

from handover.schema.task import Task
from handover.schema.trace import Verification
from handover.verify.base import Artifacts, Verdict


class ExitCodeVerifier:
    name = "exit_code"
    grade: Literal["measured", "derived"] = "measured"

    def applies_to(self, task: Task, artifacts: Artifacts) -> bool:
        return artifacts.exit_code is not None

    def verify(self, task: Task, artifacts: Artifacts) -> Verdict:
        return Verification(
            status="pass" if artifacts.exit_code == 0 else "fail",
            method="programmatic",
            signal="test_exit_code",
            confidence=1.0,
            evidence_grade="measured",
        )
