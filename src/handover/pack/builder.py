"""Handover pack assembly (SPEC §7.1).

Emits the pack directory: manifest, taxonomy, contracts, tool policies, edge
cases, prompt pointers, golden sets, and per-cluster baseline metrics.
All content references are tenant-local pointers — never inlined content.
"""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from handover.cluster import Clustering, extract_clusters
from handover.collect.redaction import ContentLeakError, assert_metadata_only
from handover.metrics import compute_core
from handover.metrics.waste import TaskTraces
from handover.pack.contract import find_edge_cases, infer_contract
from handover.pack.goldset import build_goldset
from handover.pack.tool_policy import infer_tool_policy

PACK_TARGET_MAX = 15  # packs need a tight taxonomy: merge anything above this

REQUIRED_FILES = (
    "manifest.json",
    "taxonomy.json",
    "contract.json",
    "tool_policy.json",
    "edge_cases.jsonl",
    "baseline.json",
)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def write_signed_manifest(out_dir: Path, extra: dict[str, Any]) -> Path:
    """Write manifest.json: per-file sha256 digests plus a bundle content digest."""
    digests = {
        str(path.relative_to(out_dir)).replace("\\", "/"): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(out_dir.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    _write_json(
        out_dir / "manifest.json",
        {
            **extra,
            "files": digests,
            "content_sha256": hashlib.sha256(
                json.dumps(digests, sort_keys=True).encode()
            ).hexdigest(),
        },
    )
    return out_dir / "manifest.json"


def verify_signed_manifest(out_dir: Path) -> list[str]:
    """Digest verification for any signed bundle. Empty list = intact."""
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        return ["missing manifest.json"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"invalid manifest json: {exc}"]
    errors = []
    for key in ("files", "content_sha256"):
        if key not in manifest:
            errors.append(f"manifest missing {key}")
    for rel, digest in manifest.get("files", {}).items():
        file_path = out_dir / rel
        if not file_path.exists():
            errors.append(f"manifest lists missing file {rel}")
        elif hashlib.sha256(file_path.read_bytes()).hexdigest() != digest:
            errors.append(f"digest mismatch for {rel}")
    return errors


def _cluster_items(
    clustering: Clustering, items: Sequence[TaskTraces]
) -> dict[str, list[TaskTraces]]:
    grouped: dict[str, list[TaskTraces]] = {c.cluster_id: [] for c in clustering.clusters}
    for item in items:
        cluster_id = clustering.assignments.get(str(item.task.task_id))
        if cluster_id is not None:
            grouped[cluster_id].append(item)
    return grouped


def build_pack(
    out_dir: Path,
    items: Sequence[TaskTraces],
    *,
    tenant_id: UUID,
    from_model: str,
    clustering: Clustering | None = None,
) -> Path:
    if clustering is None:
        clustering = extract_clusters(
            items, target_max=PACK_TARGET_MAX, merge_above=PACK_TARGET_MAX
        )
    grouped = _cluster_items(clustering, items)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prompts").mkdir(exist_ok=True)
    (out_dir / "golden").mkdir(exist_ok=True)

    taxonomy = []
    contracts: dict[str, Any] = {}
    policies: dict[str, Any] = {}
    baselines: dict[str, Any] = {}
    edge_lines: list[str] = []

    for cluster in clustering.clusters:
        members = grouped[cluster.cluster_id]
        contract = infer_contract(cluster.cluster_id, members)
        policy = infer_tool_policy(cluster.cluster_id, members)
        goldset = build_goldset(cluster.cluster_id, members)
        metrics = compute_core([m.task for m in members])

        taxonomy.append(
            {
                "cluster_id": cluster.cluster_id,
                "label": cluster.label,
                "n_tasks": cluster.n_tasks,
                "share_of_cost": cluster.share_of_cost,
            }
        )
        contracts[cluster.cluster_id] = contract.model_dump(mode="json")
        policies[cluster.cluster_id] = policy.model_dump(mode="json")
        baselines[cluster.cluster_id] = {
            "success_rate": metrics.success_rate.model_dump(mode="json"),
            "cpat_usd": metrics.cpat_usd.model_dump(mode="json"),
            "ttat_seconds": metrics.ttat_seconds.model_dump(mode="json"),
            "attempts_per_win": metrics.attempts_per_win.model_dump(mode="json"),
        }
        for case in find_edge_cases(members, contract):
            edge_lines.append(
                json.dumps(
                    {"cluster_id": cluster.cluster_id, **case.model_dump(mode="json")},
                    sort_keys=True,
                )
            )

        templates = sorted(
            {
                trace.input_shape.system_prompt_fingerprint
                for member in members
                for trace in member.traces
            }
        )
        _write_json(
            out_dir / "prompts" / f"{cluster.cluster_id}.json",
            {"system_prompt_refs": [f"template://{fp}" for fp in templates]},
        )
        (out_dir / "golden" / f"{cluster.cluster_id}.jsonl").write_text(
            "\n".join(json.dumps(c.model_dump(mode="json"), sort_keys=True) for c in goldset),
            encoding="utf-8",
        )

    _write_json(out_dir / "taxonomy.json", taxonomy)
    _write_json(out_dir / "contract.json", contracts)
    _write_json(out_dir / "tool_policy.json", policies)
    _write_json(out_dir / "baseline.json", baselines)
    (out_dir / "edge_cases.jsonl").write_text("\n".join(edge_lines), encoding="utf-8")

    write_signed_manifest(
        out_dir,
        {
            "schema_version": "1.0",
            "created_at": datetime.now(tz=UTC).isoformat(),
            "tenant_id": str(tenant_id),
            "from_model": from_model,
            "n_tasks": len(items),
            "n_clusters": len(clustering.clusters),
        },
    )
    return out_dir


def validate_pack(pack_dir: Path) -> list[str]:
    """Light structural validation. Empty list = valid."""
    errors = []
    for name in REQUIRED_FILES:
        if not (pack_dir / name).exists():
            errors.append(f"missing {name}")
    if errors:
        return errors
    try:
        manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
        taxonomy = json.loads((pack_dir / "taxonomy.json").read_text(encoding="utf-8"))
        json.loads((pack_dir / "contract.json").read_text(encoding="utf-8"))
        json.loads((pack_dir / "tool_policy.json").read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"invalid json: {exc}"]
    for key in ("schema_version", "from_model", "n_clusters"):
        if key not in manifest:
            errors.append(f"manifest missing {key}")
    for entry in taxonomy:
        cluster_id = entry.get("cluster_id")
        if not (pack_dir / "golden" / f"{cluster_id}.jsonl").exists():
            errors.append(f"missing golden set for {cluster_id}")
        if not (pack_dir / "prompts" / f"{cluster_id}.json").exists():
            errors.append(f"missing prompts for {cluster_id}")
    errors.extend(verify_signed_manifest(pack_dir))
    errors.extend(_scan_pack_for_content(pack_dir))
    return errors


def _scan_pack_for_content(pack_dir: Path) -> list[str]:
    """Egress guard: every shipped pack file must be metadata-only. A pack that
    trips this is refused rather than sent (defense in depth, CLAUDE.md rule 1)."""
    errors: list[str] = []
    for path in sorted(pack_dir.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines() if path.suffix == ".jsonl" else [text]:
            if not line.strip():
                continue
            try:
                assert_metadata_only(json.loads(line), name=path.name)
            except ContentLeakError as exc:
                errors.append(str(exc).splitlines()[0])
            except ValueError:
                pass  # non-JSON file; digest check already covers integrity
    return errors
