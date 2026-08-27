"""Grade A: the output parses as JSON and validates against an expected schema."""

import json
from typing import Literal

from jsonschema import Draft202012Validator

from handover.schema.task import Task
from handover.schema.trace import Verification
from handover.verify.base import Artifacts, Verdict


class JsonSchemaVerifier:
    name = "json_schema"
    grade: Literal["measured", "derived"] = "measured"

    def applies_to(self, task: Task, artifacts: Artifacts) -> bool:
        return artifacts.json_schema is not None and artifacts.output_text is not None

    def verify(self, task: Task, artifacts: Artifacts) -> Verdict:
        assert artifacts.json_schema is not None and artifacts.output_text is not None
        passed = False
        try:
            parsed = json.loads(artifacts.output_text)
        except ValueError:
            passed = False
        else:
            validator = Draft202012Validator(artifacts.json_schema)
            passed = next(iter(validator.iter_errors(parsed)), None) is None
        return Verification(
            status="pass" if passed else "fail",
            method="programmatic",
            signal="schema_validation",
            confidence=1.0,
            evidence_grade="measured",
        )
