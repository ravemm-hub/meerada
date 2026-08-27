"""Task taxonomy extraction (SPEC §7.2 step 1).

Feature vector per task from: system-prompt template fingerprint (dominant),
tool-sequence signature, and output shape. HDBSCAN over those features; target
8-15 clusters; auto-merge when over 20. Pure metadata — no content, no model
calls (labels are labeler.py's job).
"""

import math
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
from pydantic import BaseModel, ConfigDict
from sklearn.cluster import HDBSCAN

from handover.metrics.waste import TaskTraces
from handover.schema.trace import Trace

TARGET_MAX = 15
MERGE_ABOVE = 20

_TEMPLATE_WEIGHT = 3.0
_TOOLSIG_WEIGHT = 2.0

_OUTPUT_TYPES = ("json", "text", "code", "mixed")


class Cluster(BaseModel):
    model_config = ConfigDict(frozen=True)

    cluster_id: str
    n_tasks: int
    total_cost_usd: Decimal
    share_of_cost: float
    representative_task_ids: tuple[UUID, ...]
    label: str | None = None


class Clustering(BaseModel):
    model_config = ConfigDict(frozen=True)

    clusters: tuple[Cluster, ...]
    assignments: dict[str, str]  # task_id -> cluster_id


def _representative_trace(item: TaskTraces) -> Trace:
    """The trace that defines the task: its successful attempt, else the last one."""
    for trace in reversed(item.traces):
        if trace.verification.status == "pass":
            return trace
    return item.traces[-1]


def _tool_signature(trace: Trace) -> str:
    return ">".join(call.name for call in trace.tool_calls) or "<none>"


def _features(reps: Sequence[Trace]) -> "np.ndarray[Any, Any]":
    templates = sorted({t.input_shape.system_prompt_fingerprint for t in reps})
    toolsigs = sorted({_tool_signature(t) for t in reps})
    template_index = {fp: i for i, fp in enumerate(templates)}
    toolsig_index = {sig: i for i, sig in enumerate(toolsigs)}

    dim = len(templates) + len(toolsigs) + len(_OUTPUT_TYPES) + 3
    matrix = np.zeros((len(reps), dim), dtype=np.float64)
    for row, trace in enumerate(reps):
        matrix[row, template_index[trace.input_shape.system_prompt_fingerprint]] = _TEMPLATE_WEIGHT
        matrix[row, len(templates) + toolsig_index[_tool_signature(trace)]] = _TOOLSIG_WEIGHT
        base = len(templates) + len(toolsigs)
        matrix[row, base + _OUTPUT_TYPES.index(trace.output_shape.type)] = 1.0
        base += len(_OUTPUT_TYPES)
        matrix[row, base] = 1.0 if trace.output_shape.json_valid else 0.0
        matrix[row, base + 1] = 1.0 if trace.output_shape.has_code_block else 0.0
        matrix[row, base + 2] = math.log1p(trace.output_shape.n_chars) / 10.0
    return matrix


def _fallback_by_template(reps: Sequence[Trace]) -> "np.ndarray[Any, Any]":
    templates = sorted({t.input_shape.system_prompt_fingerprint for t in reps})
    index = {fp: i for i, fp in enumerate(templates)}
    return np.array([index[t.input_shape.system_prompt_fingerprint] for t in reps])


def _centroids(matrix: "np.ndarray[Any, Any]", labels: "np.ndarray[Any, Any]") -> dict[int, Any]:
    return {
        int(label): matrix[labels == label].mean(axis=0)
        for label in np.unique(labels)
        if label != -1
    }


def _merge_smallest(
    labels: "np.ndarray[Any, Any]", matrix: "np.ndarray[Any, Any]", target_max: int
) -> "np.ndarray[Any, Any]":
    labels = labels.copy()
    while len(np.unique(labels)) > target_max:
        centroids = _centroids(matrix, labels)
        sizes = {label: int((labels == label).sum()) for label in centroids}
        smallest = min(sizes, key=lambda k: sizes[k])
        others = [label for label in centroids if label != smallest]
        nearest = min(
            others,
            key=lambda k: float(np.linalg.norm(centroids[k] - centroids[smallest])),
        )
        labels[labels == smallest] = nearest
    return labels


def extract_clusters(
    items: Sequence[TaskTraces],
    *,
    target_max: int = TARGET_MAX,
    merge_above: int = MERGE_ABOVE,
    min_cluster_size: int | None = None,
) -> Clustering:
    if not items:
        return Clustering(clusters=(), assignments={})

    reps = [_representative_trace(item) for item in items]
    matrix = _features(reps)

    size = min_cluster_size or max(5, len(items) // 100)
    labels = np.asarray(HDBSCAN(min_cluster_size=size, copy=True).fit_predict(matrix))

    if (labels == -1).all():
        labels = _fallback_by_template(reps)  # degenerate case: group by template
    else:
        centroids = _centroids(matrix, labels)
        for noise_row in np.flatnonzero(labels == -1):  # assign noise to nearest centroid
            nearest = min(
                centroids,
                key=lambda k: float(np.linalg.norm(centroids[k] - matrix[noise_row])),
            )
            labels[noise_row] = nearest

    if len(np.unique(labels)) > merge_above:
        labels = _merge_smallest(labels, matrix, target_max)

    by_label: dict[int, list[int]] = {}
    for row, label in enumerate(labels):
        by_label.setdefault(int(label), []).append(row)

    total_cost = sum((item.task.total_cost_usd for item in items), Decimal("0"))
    ranked = sorted(
        by_label.items(),
        key=lambda kv: sum((items[r].task.total_cost_usd for r in kv[1]), Decimal("0")),
        reverse=True,
    )

    clusters: list[Cluster] = []
    assignments: dict[str, str] = {}
    centroids = _centroids(matrix, labels)
    for position, (label, rows) in enumerate(ranked, start=1):
        cluster_id = f"c{position:02d}"
        cost = sum((items[r].task.total_cost_usd for r in rows), Decimal("0"))
        centre = centroids.get(label, matrix[rows].mean(axis=0))
        nearest_rows = sorted(rows, key=lambda r: float(np.linalg.norm(matrix[r] - centre)))[:5]
        clusters.append(
            Cluster(
                cluster_id=cluster_id,
                n_tasks=len(rows),
                total_cost_usd=cost,
                share_of_cost=float(cost / total_cost) if total_cost else 0.0,
                representative_task_ids=tuple(items[r].task.task_id for r in nearest_rows),
            )
        )
        for r in rows:
            assignments[str(items[r].task.task_id)] = cluster_id

    return Clustering(clusters=tuple(clusters), assignments=assignments)
