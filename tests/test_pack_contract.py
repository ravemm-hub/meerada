"""T10 tests: output contract inference, field union via in-tenant loader,
tool policy with transitions and ordering constraints, edge-case ranking."""

from decimal import Decimal

from handover.pack import find_edge_cases, infer_contract, infer_tool_policy
from handover.schema.trace import Trace
from tests.factories import fp, make_trace, task_of


def json_cluster() -> list:
    items = []
    start = 0
    for i in range(8):
        items.append(
            task_of(
                make_trace(
                    start_s=start,
                    status="pass",
                    output_type="json",
                    schema_seed="schema-A",
                    n_chars=100 + i * 10,
                )
            )
        )
        start += 400
    for _ in range(2):
        items.append(
            task_of(
                make_trace(
                    start_s=start,
                    status="pass",
                    output_type="json",
                    schema_seed="schema-B",
                    n_chars=500,
                )
            )
        )
        start += 400
    # A failed task and an unknown task must not affect the contract.
    items.append(task_of(make_trace(start_s=start, status="fail", output_type="text")))
    items.append(task_of(make_trace(start_s=start + 400, status="unknown")))
    return items


def test_contract_dominant_schema_and_lengths() -> None:
    contract = infer_contract("c01", json_cluster())
    assert contract.n_successes == 10
    assert contract.dominant_type == "json"
    assert contract.json_valid_rate == 1.0
    assert contract.dominant_schema_fingerprint == fp("schema-A")
    assert contract.dominant_schema_share == 0.8
    assert contract.length.p10 <= contract.length.p50 <= contract.length.p90
    assert contract.type_shares == {"json": 1.0}


def test_contract_field_union_with_loader() -> None:
    def loader(trace: Trace) -> object | None:
        if trace.output_shape.schema_fingerprint == fp("schema-A"):
            return {"invoice_id": "x", "total": 1.5}
        return {"invoice_id": "y", "total": 2, "notes": "rare"}

    contract = infer_contract("c01", json_cluster(), output_loader=loader)
    by_name = {field.name: field for field in contract.fields}
    assert by_name["invoice_id"].presence == 1.0
    assert by_name["notes"].presence == 0.2
    assert set(by_name["total"].types) == {"float", "int"}


def test_contract_empty_cluster() -> None:
    contract = infer_contract("c09", [])
    assert contract.n_successes == 0
    assert contract.dominant_schema_fingerprint is None


def test_tool_policy_transitions_and_frequencies() -> None:
    items = [
        task_of(make_trace(start_s=i * 400, status="pass", tools=("search", "run_tests")))
        for i in range(4)
    ]
    items.append(task_of(make_trace(start_s=2000, status="pass", tools=("search", "commit"))))
    policy = infer_tool_policy("c01", items)
    assert policy.n_sequences == 5
    assert policy.tool_frequencies["search"] == 1.0
    assert policy.tool_frequencies["run_tests"] == 0.8
    top = policy.transitions[0]
    assert (top.src, top.dst, top.count) == ("search", "run_tests", 4)
    assert top.probability == 0.8  # of 5 transitions leaving "search"


def test_tool_ordering_constraint_holds_and_breaks() -> None:
    ordered = [
        task_of(make_trace(start_s=i * 400, status="pass", tools=("plan", "apply")))
        for i in range(4)
    ]
    policy = infer_tool_policy("c01", ordered)
    constraint = next(c for c in policy.constraints if c.before == "plan")
    assert constraint.after == "apply"
    assert constraint.support == 4
    assert constraint.confidence == 0.8

    # One reversed sequence kills the constraint entirely.
    broken = [*ordered, task_of(make_trace(start_s=9000, status="pass", tools=("apply", "plan")))]
    policy = infer_tool_policy("c01", broken)
    assert not any(c.before == "plan" and c.after == "apply" for c in policy.constraints)


def test_tool_policy_ignores_failures() -> None:
    items = [
        task_of(make_trace(start_s=0, status="pass", tools=("a",))),
        task_of(make_trace(start_s=400, status="fail", tools=("weird_tool",))),
    ]
    policy = infer_tool_policy("c01", items)
    assert "weird_tool" not in policy.tool_frequencies


def test_edge_cases_ranked_by_frequency_times_cost() -> None:
    items = json_cluster()
    # Two expensive successful deviants: wrong schema (already 2 in cluster at $0.10)
    # plus one type deviant with a big cost.
    items.append(
        task_of(
            make_trace(start_s=9000, status="pass", output_type="text", cost="5.00", n_chars=200)
        )
    )
    contract = infer_contract("c01", items)
    cases = find_edge_cases(items, contract)
    assert cases, "expected at least one edge case"
    signatures = {c.signature for c in cases}
    assert "type_mismatch" in signatures
    type_case = next(c for c in cases if c.signature == "type_mismatch")
    assert type_case.total_cost_usd == Decimal("5.00")
    assert 1 <= len(type_case.example_task_ids) <= 3
    # schema-B successes deviate from the dominant schema-A contract.
    assert "schema_mismatch" in signatures
