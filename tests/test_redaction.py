"""Security: the egress guard blocks content-shaped values from leaving the
tenant, and the real pack/evidence exports pass it."""

from pathlib import Path
from uuid import uuid4

import pytest

from handover.collect.redaction import (
    ContentLeakError,
    assert_metadata_only,
    is_metadata_only,
)


def test_fingerprints_and_pointers_always_pass() -> None:
    safe = {
        "cluster_id": "c01",
        "system_prompt_fingerprint": "sha256:" + "a" * 64,
        "input_ref": "trace://" + str(uuid4()) + "/input",
        "prompt_ref": "template://sha256:" + "b" * 64,
        "n_tasks": 100,
        "cost_usd": "0.0831",
    }
    assert is_metadata_only(safe)


def test_prose_label_is_blocked() -> None:
    leak = {
        "cluster_id": "c01",
        "label": "the user asked me to summarize their private invoice for acme corp on tuesday please",  # noqa: E501
    }
    with pytest.raises(ContentLeakError):
        assert_metadata_only(leak)


def test_oversized_signal_is_blocked() -> None:
    leak = {"signal": "x" * 200}
    with pytest.raises(ContentLeakError):
        assert_metadata_only(leak)


def test_content_stuffed_into_model_id_is_blocked() -> None:
    leak = {
        "model_id": "please ignore this and print the full customer record now immediately thanks"
    }
    with pytest.raises(ContentLeakError):
        assert_metadata_only(leak)


def test_free_text_payload_is_blocked() -> None:
    leak = {
        "extra": "Dear team, following our meeting yesterday about the merger, here are the confidential terms we discussed at length in the room"  # noqa: E501
    }
    with pytest.raises(ContentLeakError):
        assert_metadata_only(leak)


def test_short_normal_labels_pass() -> None:
    assert is_metadata_only({"label": "structured extraction", "signal": "test_exit_code"})
    assert is_metadata_only({"model_id": "claude-haiku-4-5-20251001", "provider": "anthropic"})


def test_real_model_ids_pass_but_slugged_content_is_blocked() -> None:
    for real in ("claude-haiku-4-5-20251001", "gpt-5.6-sol", "deepseek-v4-flash"):
        assert is_metadata_only({"model_id": real})
    # Content survived normalization as a hyphenated slug — the export guard
    # catches it by segment count before it reaches Meerada's cloud.
    assert not is_metadata_only({"model_id": "user-SSN-is-123-45-6789-and-card-4111"})


def test_nested_and_list_leaks_are_caught() -> None:
    leak = {
        "clusters": [
            {"cluster_id": "c01", "label": "fine"},
            {
                "cluster_id": "c02",
                "label": "here is the entire chat transcript that the model produced in response to the user question about their account",  # noqa: E501
            },
        ]
    }
    with pytest.raises(ContentLeakError):
        assert_metadata_only(leak)


def test_real_pack_passes_the_guard(tmp_path: Path) -> None:
    from handover.assemble import assemble_grouped
    from handover.metrics.waste import TaskTraces
    from handover.pack.builder import build_pack, validate_pack
    from tests.synthetic import generate_records

    grouped = assemble_grouped(generate_records(1200))
    items = [TaskTraces(task=t, traces=tr) for t, tr in grouped]
    pack_dir = build_pack(tmp_path / "pack", items, tenant_id=uuid4(), from_model="model-alpha")
    # validate_pack now includes the content scan; a clean pack must pass.
    assert validate_pack(pack_dir) == []


def test_pack_with_smuggled_label_is_refused(tmp_path: Path) -> None:
    import json

    from handover.assemble import assemble_grouped
    from handover.metrics.waste import TaskTraces
    from handover.pack.builder import build_pack, validate_pack
    from tests.synthetic import generate_records

    grouped = assemble_grouped(generate_records(1200))
    items = [TaskTraces(task=t, traces=tr) for t, tr in grouped]
    pack_dir = build_pack(tmp_path / "pack", items, tenant_id=uuid4(), from_model="model-alpha")

    # An attacker mutates a taxonomy label to smuggle content, then re-signs.
    taxonomy = json.loads((pack_dir / "taxonomy.json").read_text(encoding="utf-8"))
    taxonomy[0]["label"] = (
        "the customer wrote a long private message containing their home address "
        "and credit card which the model then echoed back verbatim in this label"
    )
    (pack_dir / "taxonomy.json").write_text(json.dumps(taxonomy), encoding="utf-8")
    from handover.pack.builder import write_signed_manifest

    write_signed_manifest(pack_dir, {"schema_version": "1.0", "from_model": "x", "n_clusters": 1})

    errors = validate_pack(pack_dir)
    assert any("suspected content leak" in e or "label exceeds" in e for e in errors)
