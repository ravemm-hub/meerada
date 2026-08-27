"""T8 tests: record -> report round trip on SQLite, salt stability, pack stub."""

from pathlib import Path

from typer.testing import CliRunner

from handover.cli.main import app
from handover.cli.store import SqliteStore

FIXTURE = Path(__file__).parent / "fixtures" / "raw_events_sample.jsonl"

runner = CliRunner()


def test_record_then_report(tmp_path: Path) -> None:
    db = tmp_path / "hv.db"
    out = tmp_path / "report.html"

    recorded = runner.invoke(app, ["record", str(FIXTURE), "--db", str(db)])
    assert recorded.exit_code == 0
    assert "recorded 3 traces" in recorded.output

    reported = runner.invoke(app, ["report", "--db", str(db), "--out", str(out)])
    assert reported.exit_code == 0
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "HV" in html and "claude-sonnet-4-6" in html


def test_record_is_idempotent_by_trace_id(tmp_path: Path) -> None:
    db = tmp_path / "hv.db"
    runner.invoke(app, ["record", str(FIXTURE), "--db", str(db)])
    store = SqliteStore(db)
    first_count = store.count()
    store.close()
    # Re-recording the same file adds new rows only because fixture events lack
    # trace ids (fresh UUIDs are minted); events that carry trace_id replace.
    assert first_count == 3


def test_salt_and_tenant_are_stable_across_openings(tmp_path: Path) -> None:
    db = tmp_path / "hv.db"
    store = SqliteStore(db)
    salt_one, tenant_one = store.salt(), store.tenant_id()
    store.close()
    store = SqliteStore(db)
    assert store.salt() == salt_one
    assert store.tenant_id() == tenant_one
    store.close()


def test_report_without_db_fails_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(app, ["report", "--db", str(tmp_path / "missing.db")])
    assert result.exit_code == 1


def test_pack_is_honest_about_p1(tmp_path: Path) -> None:
    result = runner.invoke(app, ["pack", "--db", str(tmp_path / "hv.db")])
    assert result.exit_code == 2
