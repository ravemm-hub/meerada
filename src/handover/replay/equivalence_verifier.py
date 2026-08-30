"""Wire output-equivalence into replay so the gap report measures quality.

Builds a ``CaseVerifier`` that judges a replayed candidate against the
incumbent's proven-good output — "as good as the model you're leaving", not
merely "well-formed". Both the expected and candidate outputs are resolved
in-tenant through injected loaders (they hold content); only the pass/fail
boolean crosses back into the replay report.
"""

from collections.abc import Callable
from typing import Any

from handover.replay.runner import ReplayCase, ReplayResult
from handover.schema.task import Task
from handover.verify import Artifacts
from handover.verify.equivalence import EquivalenceVerifier
from handover.verify.json_schema import JsonSchemaVerifier

# Resolve a pointer (expected_ref / output_ref) to its in-tenant text.
TextLoader = Callable[[str], str | None]
# Resolve a candidate output_ref to the exit code of re-running the case's tests.
ExitCodeLoader = Callable[[ReplayCase, ReplayResult], int | None]


def _placeholder_task() -> Task:
    from decimal import Decimal
    from uuid import UUID

    from handover.schema.task import TaskTokens

    return Task(
        task_id=UUID(int=0),
        tenant_id=UUID(int=0),
        attempts=1,
        succeeded=False,
        first_attempt_success=False,
        total_cost_usd=Decimal("0"),
        total_wall_ms=0,
        total_tokens=TaskTokens(input=0, output=0, reasoning=0),
        models_used=("candidate",),
        verification_grade="unknown",
    )


def equivalence_case_verifier(
    load_expected: TextLoader,
    load_candidate: TextLoader,
    *,
    exit_code_of: ExitCodeLoader | None = None,
) -> Callable[[ReplayCase, ReplayResult], bool]:
    """A CaseVerifier for replay: the candidate must be equivalent to the
    incumbent's stored expected output. Falls back to False when either output
    cannot be resolved — an unverifiable case never counts as a pass."""
    equivalence = EquivalenceVerifier()
    task = _placeholder_task()

    def verify(case: ReplayCase, result: ReplayResult) -> bool:
        expected = load_expected(case.expected_ref)
        candidate = load_candidate(result.output_ref)
        if expected is None or candidate is None:
            return False
        artifacts = Artifacts(
            output_text=candidate,
            expected_output=expected,
            candidate_exit_code=(exit_code_of(case, result) if exit_code_of else None),
        )
        return equivalence.verify(task, artifacts).status == "pass"

    return verify


def schema_case_verifier(
    load_candidate: TextLoader,
    schema_of: Callable[[ReplayCase], dict[str, Any] | None],
) -> Callable[[ReplayCase, ReplayResult], bool]:
    """A lighter CaseVerifier when there is no stored expected output but the
    cluster has a JSON contract: the candidate must at least satisfy the schema.
    Weaker than equivalence — use only where no golden output exists."""
    schema_verifier = JsonSchemaVerifier()
    task = _placeholder_task()

    def verify(case: ReplayCase, result: ReplayResult) -> bool:
        candidate = load_candidate(result.output_ref)
        schema = schema_of(case)
        if candidate is None or schema is None:
            return False
        artifacts = Artifacts(output_text=candidate, json_schema=schema)
        return schema_verifier.verify(task, artifacts).status == "pass"

    return verify
