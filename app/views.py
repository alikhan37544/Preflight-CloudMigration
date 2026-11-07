"""Read-side view models shared by the HTML routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import Manifest, Spine
from app.store import RunStore, StoreError

COLUMNS = [
    ("pcf", "PCF"),
    ("entity", "Entity"),
    ("typelist", "Typelist"),
    ("template", "Template / Gosu"),
    ("api", "API draft"),
    ("tests", "Tests"),
]


def _short_label(stem: str) -> str:
    label = stem.replace("PersonalAuto", "PA").replace("PersonalVehicle", "PV")
    label = label.replace("Personal", "")
    return label


def _column_for(node: dict[str, Any]) -> str:
    path = (node.get("artifact_path") or "").lower()
    if path.endswith(".pcf"):
        return "pcf"
    if path.endswith((".eti", ".etx")):
        return "entity"
    if path.endswith((".tti", ".ttx")):
        return "typelist"
    if "/template/" in path:
        return "template"
    if "/gtest/" in path or path.startswith("gtest/"):
        return "tests"
    if path.endswith(".gs"):
        return "template"
    if "schema" in path or "codegen" in path or "installedlobs" in path:
        return "api"
    return "entity"


def spine_layout(spine: dict[str, Any] | Spine | None) -> dict[str, Any] | None:
    if spine is None:
        return None
    data = spine.model_dump(mode="json") if isinstance(spine, Spine) else spine
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not nodes:
        return None

    columns = {
        key: {"key": key, "label": label, "nodes": [], "x": 25 + index * 145}
        for index, (key, label) in enumerate(COLUMNS)
    }
    for node in nodes:
        if node.get("kind") == "feature":
            continue
        columns[_column_for(node)]["nodes"].append(node)

    positions: dict[str, tuple[float, float]] = {}
    width = 25 + len(COLUMNS) * 145 + 20
    height = 120
    for key, column in columns.items():
        for row, node in enumerate(column["nodes"]):
            x = column["x"]
            y = 70 + row * 52
            positions[node["id"]] = (x, y)
            height = max(height, y + 90)

    svg_nodes = []
    for key in columns:
        for node in columns[key]["nodes"]:
            x, y = positions[node["id"]]
            svg_nodes.append({
                "id": node["id"],
                "label": node.get("label", "")[:22],
                "kind": node.get("kind", ""),
                "x": x,
                "y": y,
                "w": 130,
                "h": 38,
                "artifact_path": node.get("artifact_path"),
                "evidence_id": node.get("evidence_id"),
                "confidence": node.get("confidence", ""),
            })

    svg_edges = []
    for edge in edges:
        src = positions.get(edge.get("src"))
        dst = positions.get(edge.get("dst"))
        if not src or not dst:
            continue
        svg_edges.append({
            "x1": src[0] + 130,
            "y1": src[1] + 19,
            "x2": dst[0],
            "y2": dst[1] + 19,
            "kind": edge.get("kind", ""),
        })

    return {
        "columns": list(columns.values()),
        "nodes": svg_nodes,
        "edges": svg_edges,
        "width": width,
        "height": height,
    }


def _read(store: RunStore, run_id: str, name: str, default: Any) -> Any:
    try:
        return store.read_artifact(run_id, name)
    except StoreError:
        return default


def load_run_view(store: RunStore, run_id: str) -> dict[str, Any]:
    status = store.read_status(run_id)
    manifest = _read(store, run_id, "manifest.json", {"artifacts": [], "unsupported_paths": [], "file_count": 0, "sha256": "", "total_size": 0, "warnings": []})
    features = _read(store, run_id, "features.json", {"features": []})["features"]
    evidence = _read(store, run_id, "evidence.json", {"evidence": []})["evidence"]
    review_evidence = _read(store, run_id, "review_evidence.json", {"evidence": []})["evidence"]
    gaps = _read(store, run_id, "gaps.json", {"gaps": []})["gaps"]
    spine_payload = _read(store, run_id, "spine.json", {"spines": {}})
    findings_payload = _read(store, run_id, "findings.json", {"findings": [], "readiness": []})
    mappings = _read(store, run_id, "mappings.json", {"mappings": []})["mappings"]
    changes = _read(store, run_id, "changes.json", {"changes": []})["changes"]
    assumptions = _read(store, run_id, "assumptions.json", {"assumptions": []})["assumptions"]
    comparison = _read(store, run_id, "comparison.json", {"rows": [], "macro_f1": 0, "confusion": {}})
    metrics = _read(store, run_id, "metrics.json", {"metrics": [], "supporting": [], "baselines": {}, "per_rule": {}})
    packet = _read(store, run_id, "packet.json", None)
    audit = store.read_audit(run_id)
    decisions = _read(store, run_id, "decisions.json", {"decisions": []})["decisions"]
    immutability = _read(store, run_id, "immutability.json", {"before": "", "after": "", "unchanged": False})

    evidence_by_id = {item["evidence_id"]: item for item in evidence + review_evidence}
    selected_feature = features[0] if features else None
    spines = spine_payload.get("spines", {})
    selected_spine = None
    if selected_feature:
        selected_spine = spines.get(selected_feature["feature_id"])

    return {
        "status": status,
        "manifest": manifest,
        "features": features,
        "evidence": evidence,
        "review_evidence": review_evidence,
        "evidence_by_id": evidence_by_id,
        "gaps": gaps,
        "findings": findings_payload.get("findings", []),
        "readiness": findings_payload.get("readiness", []),
        "mappings": mappings,
        "changes": changes,
        "assumptions": assumptions,
        "comparison": comparison,
        "metrics": metrics,
        "packet": packet,
        "audit": audit,
        "audit_verified": store.verify_audit(run_id),
        "decisions": decisions,
        "immutability": immutability,
        "spines": spines,
        "selected_feature": selected_feature,
        "selected_spine": selected_spine,
        "spine_layout": spine_layout(selected_spine),
        "unsupported_count": len(manifest.get("unsupported_paths", [])),
    }
