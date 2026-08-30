"""Public benchmark task set for the Meerada Grade index.

Every task is programmatically verifiable (grade-A measured) — that is the
whole point: the public index only ranks on tasks we can check, never on
opinion. Tasks are grouped into clusters mirroring the canonical taxonomy so
the §4.3 within-cluster scoring applies.

These are seed tasks; the real index expands the set. Content here is public
(no tenant data), so it may ship in the open-source repo.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Cluster = Literal["structured_extraction", "code_fix", "json_transform", "classification"]


class BenchTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_id: str
    cluster: Cluster
    system: str
    user: str
    # Verifier spec: exactly one of these is set.
    json_schema: dict[str, Any] | None = None
    contract_regex: str | None = None


_EXTRACT_SCHEMA = {
    "type": "object",
    "required": ["name", "amount", "currency"],
    "properties": {
        "name": {"type": "string"},
        "amount": {"type": "number"},
        "currency": {"type": "string"},
    },
}

SEED_TASKS: tuple[BenchTask, ...] = (
    BenchTask(
        task_id="extract-01",
        cluster="structured_extraction",
        system="Extract the payee, amount and currency. Reply with JSON only.",
        user="Invoice: pay Acme Corp the sum of 1,240.50 USD by Friday.",
        json_schema=_EXTRACT_SCHEMA,
    ),
    BenchTask(
        task_id="extract-02",
        cluster="structured_extraction",
        system="Extract the payee, amount and currency. Reply with JSON only.",
        user="Transfer 89 EUR to Maria Gomez for the design work.",
        json_schema=_EXTRACT_SCHEMA,
    ),
    BenchTask(
        task_id="json-01",
        cluster="json_transform",
        system="Return a JSON object with keys 'sum' and 'count' for the numbers given.",
        user="Numbers: 4, 8, 15, 16, 23, 42.",
        json_schema={
            "type": "object",
            "required": ["sum", "count"],
            "properties": {"sum": {"type": "number"}, "count": {"type": "integer"}},
        },
    ),
    BenchTask(
        task_id="extract-03",
        cluster="structured_extraction",
        system="Extract the payee, amount and currency. Reply with JSON only.",
        user="Please remit 3450.00 GBP to Northwind Traders for invoice 88.",
        json_schema=_EXTRACT_SCHEMA,
    ),
    BenchTask(
        task_id="extract-04",
        cluster="structured_extraction",
        system="Extract the payee, amount and currency. Reply with JSON only.",
        user="Wire 12.75 CAD to Luca Rossi, thanks.",
        json_schema=_EXTRACT_SCHEMA,
    ),
    BenchTask(
        task_id="json-02",
        cluster="json_transform",
        system="Return a JSON object with keys 'sum' and 'count' for the numbers given.",
        user="Numbers: 10, 20, 30.",
        json_schema={
            "type": "object",
            "required": ["sum", "count"],
            "properties": {"sum": {"type": "number"}, "count": {"type": "integer"}},
        },
    ),
    BenchTask(
        task_id="json-03",
        cluster="json_transform",
        system="Return a JSON object with keys 'sum' and 'count' for the numbers given.",
        user="Numbers: 7, 7, 7, 7.",
        json_schema={
            "type": "object",
            "required": ["sum", "count"],
            "properties": {"sum": {"type": "number"}, "count": {"type": "integer"}},
        },
    ),
    BenchTask(
        task_id="code-01",
        cluster="code_fix",
        system="Reply with a single Python function in a ```python code block.",
        user="Write a function `is_even(n)` that returns True for even integers.",
        contract_regex=r"```python[\s\S]*def is_even\(",
    ),
    BenchTask(
        task_id="code-02",
        cluster="code_fix",
        system="Reply with a single Python function in a ```python code block.",
        user="Write `reverse_str(s)` that returns the reversed string.",
        contract_regex=r"```python[\s\S]*def reverse_str\(",
    ),
    BenchTask(
        task_id="code-03",
        cluster="code_fix",
        system="Reply with a single Python function in a ```python code block.",
        user="Write `add(a, b)` that returns the sum of two numbers.",
        contract_regex=r"```python[\s\S]*def add\(",
    ),
    BenchTask(
        task_id="classify-01",
        cluster="classification",
        system="Classify sentiment. Reply with exactly one word: positive, negative, or neutral.",
        user="The delivery was late and the box was damaged.",
        contract_regex=r"(?i)^\s*negative\.?\s*$",
    ),
    BenchTask(
        task_id="classify-02",
        cluster="classification",
        system="Classify sentiment. Reply with exactly one word: positive, negative, or neutral.",
        user="Absolutely loved it — fast, friendly and flawless!",
        contract_regex=r"(?i)^\s*positive\.?\s*$",
    ),
    BenchTask(
        task_id="classify-03",
        cluster="classification",
        system="Classify sentiment. Reply with exactly one word: positive, negative, or neutral.",
        user="The package arrived on Tuesday.",
        contract_regex=r"(?i)^\s*neutral\.?\s*$",
    ),
)


def tasks_by_cluster() -> dict[str, list[BenchTask]]:
    grouped: dict[str, list[BenchTask]] = {}
    for task in SEED_TASKS:
        grouped.setdefault(task.cluster, []).append(task)
    return grouped
