"""Grade A: the output satisfies an explicit regex contract."""

import re
from typing import Literal

from handover.schema.task import Task
from handover.schema.trace import Verification
from handover.verify.base import Artifacts, Verdict


class RegexContractVerifier:
    name = "regex_contract"
    grade: Literal["measured", "derived"] = "measured"

    def applies_to(self, task: Task, artifacts: Artifacts) -> bool:
        return artifacts.contract_regex is not None and artifacts.output_text is not None

    def verify(self, task: Task, artifacts: Artifacts) -> Verdict:
        assert artifacts.contract_regex is not None and artifacts.output_text is not None
        passed = re.search(artifacts.contract_regex, artifacts.output_text) is not None
        return Verification(
            status="pass" if passed else "fail",
            method="programmatic",
            signal="regex_contract",
            confidence=1.0,
            evidence_grade="measured",
        )
