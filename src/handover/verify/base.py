"""Verifier protocol (SPEC §5.3) and the registry that picks the strongest verdict.

Note: ``applies_to`` also receives the artifacts — applicability is determined
by which evidence exists for the task, which the Task record alone cannot tell.
"""

from collections.abc import Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from handover.schema.task import Task
from handover.schema.trace import Verification

Verdict = Verification

# No applicable verifier: the task is excluded from all metrics (SPEC §3.2 rule 4).
UNKNOWN = Verification(
    status="unknown",
    method="programmatic",
    signal="none",
    confidence=0.0,
    evidence_grade="declared",
)

_GRADE_RANK: dict[str, int] = {"measured": 0, "derived": 1}


class Artifacts(BaseModel):
    """In-tenant evidence available for verifying one task. Never leaves the tenant."""

    model_config = ConfigDict(frozen=True)

    exit_code: int | None = None
    output_text: str | None = None
    json_schema: dict[str, Any] | None = None
    contract_regex: str | None = None
    accepted_downstream: bool | None = None
    retried_within_10m: bool | None = None
    correction_followed: bool | None = None


@runtime_checkable
class Verifier(Protocol):
    name: str
    grade: Literal["measured", "derived"]

    def applies_to(self, task: Task, artifacts: Artifacts) -> bool: ...

    def verify(self, task: Task, artifacts: Artifacts) -> Verdict: ...


class VerifierRegistry:
    """Runs every applicable verifier. The strongest evidence grade wins; within
    that grade any fail wins — a success must satisfy all applicable checks."""

    def __init__(self, verifiers: Sequence[Verifier]) -> None:
        self._verifiers = list(verifiers)

    def verify(self, task: Task, artifacts: Artifacts) -> Verdict:
        verdicts = [
            (_GRADE_RANK[verifier.grade], verifier.verify(task, artifacts))
            for verifier in self._verifiers
            if verifier.applies_to(task, artifacts)
        ]
        if not verdicts:
            return UNKNOWN
        best = min(rank for rank, _ in verdicts)
        top = [verdict for rank, verdict in verdicts if rank == best]
        failed = next((verdict for verdict in top if verdict.status == "fail"), None)
        return failed or top[0]


def default_registry() -> VerifierRegistry:
    from handover.verify.exit_code import ExitCodeVerifier
    from handover.verify.json_schema import JsonSchemaVerifier
    from handover.verify.regex_contract import RegexContractVerifier
    from handover.verify.silent_acceptance import SilentAcceptanceVerifier

    return VerifierRegistry(
        [
            ExitCodeVerifier(),
            JsonSchemaVerifier(),
            RegexContractVerifier(),
            SilentAcceptanceVerifier(),
        ]
    )
