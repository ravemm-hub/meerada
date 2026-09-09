"""The battery's checkers: a task passes only when a program says so.
Outputs here are hand-written stand-ins for model replies — no live API."""
# ruff: noqa: E501

import pytest

from handover.bench import verify_tasks as vt
from handover.bench.tasks import TASKS, BenchTask, tasks_by_cluster


def _task(task_id: str) -> BenchTask:
    return next(t for t in TASKS if t.task_id == task_id)


def test_every_task_carries_its_checker_payload() -> None:
    for t in TASKS:
        need = {
            "code_tests": t.tests, "sql": t.sql_setup and t.reference_sql,
            "json_values": t.expected, "exact": t.answer, "faithful": t.source,
            "regex": t.contract_regex, "schema": t.json_schema,
        }[t.check]
        assert need, f"{t.task_id} lacks payload for {t.check}"
    assert len(TASKS) >= 20 and len(tasks_by_cluster()) == 8


def test_code_hidden_tests_pass_and_fail() -> None:
    good = '''```python
import re
def parse_duration(s):
    m = re.fullmatch(r"P(?:(\\d+)D)?(?:T(?:(\\d+)H)?(?:(\\d+)M)?(?:(\\d+)S)?)?", s or "")
    if not m or s in ("P", "PT") or not any(m.groups()):
        raise ValueError(s)
    d, h, mi, se = (int(x) if x else 0 for x in m.groups())
    return d*86400 + h*3600 + mi*60 + se
```'''
    assert vt.verify_task(_task("code-iso-duration"), good)
    lenient = "```python\ndef parse_duration(s):\n    return 5400\n```"  # ignores input
    assert not vt.verify_task(_task("code-iso-duration"), lenient)
    assert not vt.verify_task(_task("code-iso-duration"), "I'd write a parser like this...")
    hangs = "```python\ndef parse_duration(s):\n    while True: pass\n```"
    vt.CODE_TIMEOUT_S = 2
    assert not vt.verify_task(_task("code-iso-duration"), hangs)  # timeout -> fail, no hang


def test_merge_intervals_reference_solution_passes() -> None:
    sol = '''```python
def merge(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out
```'''
    assert vt.verify_task(_task("code-merge-intervals"), sol)


def test_sql_runs_against_real_db_and_compares_rows() -> None:
    t = _task("sql-no-orders")
    assert vt.verify_task(t, "```sql\nSELECT name FROM customers c WHERE NOT EXISTS "
                             "(SELECT 1 FROM orders o WHERE o.customer_id=c.id) ORDER BY name\n```")
    assert not vt.verify_task(t, "```sql\nSELECT name FROM customers ORDER BY name\n```")
    assert not vt.verify_task(t, "```sql\nDROP TABLE customers; SELECT 1\n```")  # not a single SELECT
    assert not vt.verify_task(t, "```sql\nSELECT nme FROM customers\n```")  # bad SQL -> fail
    rev = _task("sql-net-revenue")
    # a different but correct formulation passes; forgetting refunds fails
    # a correlated subquery must sit INSIDE the aggregate — outside it, SQLite evaluates it for
    # one arbitrary row per group, and the checker rightly rejects that version
    ok = ("```sql\nSELECT c.country, ROUND(SUM(o.amount - COALESCE((SELECT SUM(r.amount) FROM refunds r "
          "WHERE r.order_id=o.id),0)),2) AS net FROM orders o JOIN customers c ON c.id=o.customer_id "
          "WHERE o.status='completed' AND o.ordered_at>='2026-01-01' AND o.ordered_at<='2026-03-31' "
          "GROUP BY c.country ORDER BY net DESC\n```")
    assert vt.verify_task(rev, ok)
    no_refunds = ("```sql\nSELECT c.country, SUM(o.amount) FROM orders o JOIN customers c ON c.id=o.customer_id "
                  "WHERE o.status='completed' AND o.ordered_at BETWEEN '2026-01-01' AND '2026-03-31' "
                  "GROUP BY c.country ORDER BY 2 DESC\n```")
    assert not vt.verify_task(rev, no_refunds)


def test_json_values_checks_values_not_just_shape() -> None:
    t = _task("extract-invoice")
    good = ('{"vendor":"Northwind Traders Ltd.","invoice_number":"A-2291","currency":"EUR",'
            '"subtotal":135.50,"total_due":145.12,"due_date":"2026-09-13"}')
    assert vt.verify_task(t, "Here you go:\n" + good)
    wrong_total = good.replace("145.12", "135.50")
    assert not vt.verify_task(t, wrong_total)
    assert not vt.verify_task(t, good.replace("2026-09-13", "2026-08-14"))  # invoice date != due date
    tool = _task("tool-refund")
    assert vt.verify_task(tool, '{"tool":"refund_order","args":{"order_id":"A1092","amount":35,"reason":"broken"}}')
    assert not vt.verify_task(tool, '{"tool":"lookup_order","args":{"order_id":"A1092"}}')


def test_exact_reads_the_answer_line_with_tolerance() -> None:
    t = _task("reason-units")
    assert vt.verify_task(t, "Net fill 10 L/min; 2500/10 = 250.\nANSWER: 250")
    assert vt.verify_task(t, "ANSWER: 250 minutes")
    assert not vt.verify_task(t, "ANSWER: 208")
    cal = _task("reason-calendar")
    assert vt.verify_task(cal, "...\nANSWER: 2026-10-09")
    assert not vt.verify_task(cal, "ANSWER: 2026-10-08")
    assert vt.verify_task(_task("longctx-policy"), "4 days x 71 = 284\nANSWER: 284")
    assert not vt.verify_task(_task("longctx-policy"), "ANSWER: 426")  # 6 x 71: ignored the cap


def test_faithful_summary_requires_facts_and_forbids_invented_numbers() -> None:
    t = _task("summary-quarter")
    good = "Revenue hit 4.8M (+12% YoY) but gross margin fell to 61%; churn steady at 2.1%."
    assert vt.verify_task(t, good)
    assert not vt.verify_task(t, "Revenue hit 4.8M, up 12%; margin 61%.")  # churn missing
    assert not vt.verify_task(t, good + " Headcount is now 50.")  # 50 is invented
    assert not vt.verify_task(t, "")


@pytest.mark.parametrize("bad", ["Positive", "neutral"])
def test_regex_classification_still_strict(bad: str) -> None:
    t = _task("classify-sarcasm")
    assert vt.verify_task(t, "negative")
    assert not vt.verify_task(t, bad)
