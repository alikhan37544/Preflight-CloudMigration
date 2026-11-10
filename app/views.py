"""Read-side view models shared by the HTML routes."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.models import Confidence, Manifest, Spine, SpineNode
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


def _break_word(word: str, limit: int) -> list[str]:
    """Split an over-long camel-case label at readable boundaries."""
    if len(word) <= limit:
        return [word]
    boundaries = [
        index for index in range(2, len(word))
        if word[index].isupper() and word[index - 1].islower()
    ]
    fitting = [index for index in boundaries if index <= limit]
    split = max(fitting) if fitting else limit
    return [word[:split]] + _break_word(word[split:], limit)


def _wrap_label(label: str, limit: int = 15, max_lines: int = 2) -> list[str]:
    """Wrap an SVG label without relying on browser text measurement.

    Column widths in ``spine_layout`` are computed from these lines. Keeping
    the wrapper deliberately conservative (15 characters at 10px) means the
    graph fits a 1280px workbench while labels stay at or above 10px.
    """
    chunks: list[tuple[str, str]] = []
    for word_index, word in enumerate(label.split()):
        pieces = _break_word(word, limit)
        for piece_index, piece in enumerate(pieces):
            separator = "" if piece_index else (" " if word_index else "")
            chunks.append((piece, separator))

    lines: list[str] = []
    current = ""
    for piece, separator in chunks:
        candidate = f"{current}{separator}{piece}" if current else piece
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = piece
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: limit - 1] + "\u2026"
    return lines or [label[:limit]]


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

    # Labels are wrapped to at most 15 characters at 10px. Each column width is
    # computed from its longest wrapped line (minimum 100px), which keeps all
    # six columns inside a 1280px workbench without shrinking text below 10px.
    char_width = 5.6
    gap = 10
    left = 14
    top = 58
    row_gap = 8
    min_width = 100
    columns: dict[str, dict[str, Any]] = {
        key: {
            "key": key,
            "label": label,
            "header_lines": _wrap_label(label, limit=13, max_lines=2),
            "nodes": [],
            "x": 0,
            "width": min_width,
        }
        for key, label in COLUMNS
    }
    for node in nodes:
        if node.get("kind") == "feature":
            continue
        columns[_column_for(node)]["nodes"].append(node)

    for column in columns.values():
        longest = max(
            [len(line) for line in column["header_lines"]]
            + [len(line) for node in column["nodes"]
               for line in _wrap_label(node.get("label", ""), limit=15)]
            + [8]  # the kind caption, e.g. "artifact"
        )
        column["width"] = max(min_width, round(14 + longest * char_width))

    x = left
    for column in columns.values():
        column["x"] = x
        x += column["width"] + gap
    width = x - gap + 8

    positions: dict[str, tuple[float, float, float, float]] = {}
    height = top + 90
    for column in columns.values():
        y = top
        for node in column["nodes"]:
            label_lines = _wrap_label(node.get("label", ""), limit=15)
            node_height = 44 if len(label_lines) == 1 else 56
            positions[node["id"]] = (column["x"], y, node_height, column["width"])
            y += node_height + row_gap
            height = max(height, y + 10)

    svg_nodes = []
    for column in columns.values():
        for node in column["nodes"]:
            x, y, node_height, node_width = positions[node["id"]]
            svg_nodes.append({
                "id": node["id"],
                "label": node.get("label", ""),
                "label_lines": _wrap_label(node.get("label", ""), limit=15),
                "kind": node.get("kind", ""),
                "x": x,
                "y": y,
                "w": column["width"],
                "h": node_height,
                "kind_y": node_height - 8,
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
            "x1": src[0] + src[3],
            "y1": src[1] + src[2] / 2,
            "x2": dst[0],
            "y2": dst[1] + dst[2] / 2,
            "kind": edge.get("kind", ""),
        })

    return {
        "columns": list(columns.values()),
        "nodes": svg_nodes,
        "edges": svg_edges,
        "width": width,
        "height": height,
    }


PRECISION_GUARDS = [
    {
        "rule_id": "PF-GW-SQL-001",
        "title": "Direct JDBC or SQL access",
        "negatives": [
            ("Query.make(PersonalVehicle).select()", "supported data-access API, not JDBC"),
            ("DriverManager.getConnection(...) in a comment or string", "comments and strings are masked before matching"),
            ('client.executeQuery("search")', "non-JDBC search call is not direct SQL access"),
        ],
    },
    {
        "rule_id": "PF-GW-SEC-001",
        "title": "Hard-coded secret",
        "negatives": [
            ('password = "CHANGEME" / "<placeholder>" / "${API_KEY}"', "documented placeholders and env references are ignored"),
            ('apiKey = System.getenv("API_KEY")', "environment lookup is not a hard-coded value"),
            ('password = "hunter2" in a comment', "comments are masked before the assignment scan"),
        ],
    },
    {
        "rule_id": "PF-GW-PKG-001",
        "title": "Hidden or internal package reference",
        "negatives": [
            ("uses com.guidewire.public.api.Thing", "public Guidewire namespace is allowed"),
            ("// gw.internal.util in a comment", "comment prose is masked"),
            ("uses gw.api.database.Query", "supported public data API is not an internal package"),
        ],
    },
    {
        "rule_id": "PF-GW-EXC-001",
        "title": "Swallowed exception",
        "negatives": [
            ('catch (e : Exception) { throw new RuntimeException("vehicle lookup failed", e) }', "rethrow with context is not suppression"),
            ("// catch (...) { } in prose", "commented code is masked"),
            ("SafePatterns.gs with no catch block", "absence of a catch is not a finding"),
        ],
    },
    {
        "rule_id": "PF-GW-TX-001",
        "title": "Explicit commit inside runWithNewBundle",
        "negatives": [
            ("bundle.commit() outside runWithNewBundle", "commit is only flagged inside the managed block"),
            ("// bundle.commit() in a comment", "comment prose is masked"),
            ("runWithNewBundle { bundle.add(vehicle) } with no commit", "managed block without an explicit commit is clean"),
        ],
    },
    {
        "rule_id": "PF-GW-SRV-001",
        "title": "Custom servlet",
        "negatives": [
            ("// class X extends HttpServlet in prose", "comments are masked"),
            ("com.guidewire.public.api.Thing", "public API integration is not a servlet"),
            ("SearchClient.gs with no servlet import", "plain integration code is not flagged"),
        ],
    },
    {
        "rule_id": "PF-GW-NAM-001",
        "title": "APD type name exceeds 24 characters",
        "negatives": [
            ("A" * 24, "exactly 24 characters is at the documented limit, not over it"),
            ("PAVehicle / PACoverage", "short type names are untouched"),
            ("ShortTypes.xml / ShortTypesB.xml", "short names in adjacent templates are not flagged"),
        ],
    },
    {
        "rule_id": "PF-GW-GUNIT-001",
        "title": "Database access in a pure unit test",
        "negatives": [
            ("PersonalVehicleValidationTest.gs", "validation test has no DB calls"),
            ("PersonalVehiclePureTest.gs", "pure math assertions only"),
            ("PersonalVehiclePureTestB.gs", "pure math assertions only"),
        ],
    },
]


def _evidence_group(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".pcf"):
        return "pcf"
    if lower.endswith((".eti", ".etx")):
        return "entity"
    if lower.endswith((".tti", ".ttx")):
        return "typelist"
    if "/template/" in lower or lower.startswith("product/template/"):
        return "template"
    if "/gtest/" in lower or lower.startswith("gtest/"):
        return "test"
    if lower.endswith(".gs"):
        return "gosu"
    return "other"


LONG_TYPE_RULE = "PF-GW-NAM-001"
RECONSTRUCTION_FEATURE_ID = "PA-VEH-01"


def _type_name_length(finding: dict[str, Any],
                      evidence_by_id: dict[str, Any]) -> int | None:
    """Return the actual type-name length, never a hard-coded demo value."""
    match = re.search(r"APD type '([^']+)'", finding.get("message", ""))
    if match:
        return len(match.group(1))
    for evidence_id in finding.get("evidence_ids", []):
        evidence = evidence_by_id.get(evidence_id) or {}
        match = re.search(r'<type\s+name="([^"]+)"', evidence.get("excerpt", ""))
        if match:
            return len(match.group(1))
    match = re.search(r"(\d+)\s+characters", finding.get("message", ""))
    return int(match.group(1)) if match else None


def _finding_in_feature_scope(finding: dict[str, Any], feature_id: str,
                              feature_evidence_ids: set[str],
                              feature_paths: set[str],
                              evidence_by_id: dict[str, Any],
                              mapping_names: set[str]) -> bool:
    evidence_ids = set(finding.get("evidence_ids", []))
    if evidence_ids & feature_evidence_ids:
        return True
    if any(
        (evidence_by_id.get(evidence_id) or {}).get("path") in feature_paths
        for evidence_id in evidence_ids
    ):
        return True
    # The reconstruction slice (PA-VEH-01) carries the documented 24-char
    # mapping. A finding naming one of that slice's mapping types is in scope
    # even though review evidence has its own REV-* IDs.
    if feature_id == RECONSTRUCTION_FEATURE_ID and finding.get("rule_id") == LONG_TYPE_RULE:
        message = finding.get("message", "")
        return any(name and name in message for name in mapping_names)
    return False


def feature_summary(view: dict[str, Any]) -> dict[str, Any] | None:
    """Compact first-beat metrics derived from the selected feature's real evidence."""
    feature = view.get("selected_feature")
    if not feature:
        return None
    feature_id = feature.get("feature_id", "")
    by_id = view.get("evidence_by_id", {})
    feature_evidence_ids = set(feature.get("evidence_ids", []))
    items = [by_id[eid] for eid in feature.get("evidence_ids", []) if eid in by_id]
    paths = {item.get("path", "") for item in items}
    groups = {_evidence_group(path) for path in paths}
    spine = view.get("selected_spine") or {}
    if hasattr(spine, "model_dump"):
        spine = spine.model_dump(mode="json")
    edges = spine.get("edges", [])

    mapping_names: set[str] = set()
    if feature_id == RECONSTRUCTION_FEATURE_ID:
        for mapping in view.get("mappings", []):
            mapping_names.update(
                name for name in (mapping.get("source_ref"), mapping.get("target_name")) if name
            )

    long_type = None
    long_type_finding = None
    for finding in view.get("findings", []):
        if finding.get("rule_id") != LONG_TYPE_RULE:
            continue
        if not _finding_in_feature_scope(
            finding, feature_id, feature_evidence_ids, paths, by_id, mapping_names
        ):
            continue
        long_type = _type_name_length(finding, by_id)
        long_type_finding = finding
        break

    gaps = view.get("gaps", [])
    feature_gaps = [
        gap for gap in gaps
        if gap.get("feature_id") == feature_id
        or feature_evidence_ids.intersection(gap.get("evidence_ids", []) or [])
    ]
    if feature_gaps:
        gap_count, gap_label = len(feature_gaps), "feature gaps"
    else:
        gap_count, gap_label = len(gaps), "estate gaps"

    return {
        "feature_id": feature_id,
        "feature_name": feature.get("name", ""),
        "evidence": len(items),
        "files": len(paths),
        "artifact_types": len(groups & {"pcf", "entity", "typelist", "template"}),
        "tests": len({path for path in paths if _evidence_group(path) == "test"}),
        "references": len([edge for edge in edges if edge.get("kind") != "tested_by"]),
        "long_type": long_type,
        "long_type_finding": long_type_finding,
        "gaps": gap_count,
        "gaps_label": gap_label,
    }


BASELINE_LABELS = {
    "identity_mapper": "Identity mapper",
    "normalized_name_mapper": "Normalized-name mapper",
    "pcf_grep_discovery": "PCF filename baseline",
    "grep_only_findings": "Grep-only findings (precision)",
    "grep_only_findings_f1": "Grep-only F1",
    "all_unresolved": "All-unresolved",
}
BASELINE_ORDER = [
    "identity_mapper", "normalized_name_mapper", "pcf_grep_discovery",
    "grep_only_findings", "grep_only_findings_f1", "all_unresolved",
]
def _pct(value: Any, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "-"


def _fraction(metric: dict[str, Any] | None) -> str:
    if not metric:
        return "-"
    return f"{metric.get('numerator', 0)}/{metric.get('denominator', 0)}"


def _metric_aria(metric: dict[str, Any]) -> str:
    label = f"{metric.get('metric_id', '')} {metric.get('label', '')}: {_pct(metric.get('value'))}"
    low = metric.get("interval_low")
    high = metric.get("interval_high")
    if low is None or high is None:
        return f"{label}; no interval; bootstrap deferred."
    return f"{label}; 95% Wilson interval {_pct(low)} to {_pct(high)}."


def evaluation_view(view: dict[str, Any]) -> dict[str, Any]:
    """Pre-compute display rows so every number comes from metrics.json."""
    payload = view.get("metrics") or {}
    metrics = payload.get("metrics", [])
    supporting = payload.get("supporting", [])
    by_id = {metric.get("metric_id"): metric for metric in metrics}
    supporting_by_id = {metric.get("metric_id"): metric for metric in supporting}
    per_rule = payload.get("per_rule", {}) or {}
    margins = payload.get("margins", {}) or {}
    baselines = payload.get("baselines", {}) or {}

    m5 = by_id.get("M5")
    m6 = by_id.get("M6")
    top8 = supporting_by_id.get("M5-TOP8")
    holdout = supporting_by_id.get("HOLDOUT-RECALL")

    hard_negatives = len(per_rule) * 3
    false_positives = sum(int(stats.get("fp", 0) or 0) for stats in per_rule.values())
    silent_negatives = max(0, hard_negatives - min(false_positives, hard_negatives))

    m6_counts = None
    if m6:
        m6_tp = sum(int(stats.get("tp", 0) or 0) for stats in per_rule.values())
        m6_fp = sum(int(stats.get("fp", 0) or 0) for stats in per_rule.values())
        m6_fn = sum(int(stats.get("fn", 0) or 0) for stats in per_rule.values())
        m6_counts = {
            "tp": m6_tp,
            "fp": m6_fp,
            "fn": m6_fn,
            "findings": m6_tp + m6_fp,
            "f1": f"{float(m6.get('value', 0)):.2f}",
            "detail": (
                f"F1 {float(m6.get('value', 0)):.2f} \u00b7 "
                f"{m6_tp} TP / {m6_fp} FP / {m6_fn} FN"
            ),
        }

    facts = []
    if m5:
        facts.append({"value": _fraction(m5), "label": "estimate-moving issues",
                      "title": "M5 recall"})
    if m6 and m6_counts:
        facts.append({
            "value": f"{m6_counts['findings']} findings",
            "label": f"micro-F1 {m6_counts['f1']}",
            "title": (
                f"M6 micro-F1 {m6_counts['f1']} from {m6_counts['tp']} true positives, "
                f"{m6_counts['fp']} false positives, and {m6_counts['fn']} false negatives"
            ),
        })
    if holdout:
        facts.append({"value": _fraction(holdout), "label": "holdout recall (not imported)",
                      "title": "Pre-computed holdout aggregate; never imported"})
    if top8:
        facts.append({"value": _fraction(top8), "label": "top-8 allowance",
                      "title": "M5 top-8 slots"})
    if hard_negatives:
        facts.append({"value": f"{silent_negatives}/{hard_negatives}",
                      "label": "hard negatives silent",
                      "title": "Labelled hard negatives with no false positive"})
    facts.append({"value": "", "label": "all metrics in-sample on one synthetic fixture",
                  "title": "No claim beyond the synthetic demo slice", "wide": True})

    chart_rows = []
    for metric in metrics:
        if metric.get("metric_id") not in {"M1", "M2", "M3", "M4", "M5", "M6"}:
            continue
        low = metric.get("interval_low")
        high = metric.get("interval_high")
        has_interval = low is not None and high is not None
        metric_id = metric.get("metric_id")
        chart_rows.append({
            "id": metric_id,
            "label": metric.get("label", ""),
            "value_pct": _pct(metric.get("value")),
            "fraction": (
                f"{m6_counts['findings']} findings \u00b7 F1 {m6_counts['f1']}"
                if metric_id == "M6" and m6_counts else _fraction(metric)
            ),
            "dot_left": f"{float(metric.get('value', 0)) * 100:.2f}",
            "has_interval": has_interval,
            "interval_left": f"{float(low) * 100:.2f}" if has_interval else "0",
            "interval_right": f"{float(high) * 100:.2f}" if has_interval else "0",
            "interval_text": (
                f"{_pct(low)}–{_pct(high)}" if has_interval
                else "no interval (bootstrap deferred)"
            ),
            "aria": _metric_aria(metric),
        })

    short_labels = {
        "M1": "Feature discovery recall",
        "M4": "Disposition correctness",
        "M6": "Finding micro-F1",
    }
    baseline_keys = {"M1": "pcf_grep_discovery", "M4": "identity_mapper", "M6": "grep_only_findings_f1"}
    bar_rows = []
    for metric_id in ("M1", "M4", "M6"):
        metric = by_id.get(metric_id)
        margin = margins.get(metric_id)
        if not metric or not margin:
            continue
        baseline_key = baseline_keys[metric_id]
        bar_rows.append({
            "id": metric_id,
            "label": short_labels.get(metric_id, metric.get("label", "")),
            "value_pct": _pct(metric.get("value")),
            "value_left": f"{float(metric.get('value', 0)) * 100:.2f}",
            "baseline_pct": _pct(margin.get("baseline")),
            "baseline_left": f"{float(margin.get('baseline', 0)) * 100:.2f}",
            "baseline_label": BASELINE_LABELS.get(baseline_key, baseline_key),
            "delta_pp": f"{float(margin.get('delta', 0)) * 100:+.1f} pp",
            "pass": bool(margin.get("pass")),
        })

    baseline_rows = []
    for key in BASELINE_ORDER:
        if key not in baselines:
            continue
        baseline_rows.append({
            "key": key,
            "label": BASELINE_LABELS.get(key, key.replace("_", " ")),
            "value_pct": _pct(baselines[key]),
        })

    margin_rows = []
    for metric_id, margin in margins.items():
        baseline_key = baseline_keys.get(metric_id, "")
        margin_rows.append({
            "id": metric_id,
            "label": short_labels.get(metric_id, metric_id),
            "baseline_pct": _pct(margin.get("baseline")),
            "baseline_label": BASELINE_LABELS.get(baseline_key, "baseline"),
            "delta_pp": f"{float(margin.get('delta', 0)) * 100:+.1f} pp",
            "required_pp": f"+{float(margin.get('required_pp', 0)):.0f} pp",
            "pass": bool(margin.get("pass")),
        })

    per_rule_rows = []
    for rule_id, stats in per_rule.items():
        tp, fp, fn = int(stats.get("tp", 0)), int(stats.get("fp", 0)), int(stats.get("fn", 0))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        per_rule_rows.append({
            "rule_id": rule_id, "tp": tp, "fp": fp, "fn": fn,
            "precision_pct": _pct(precision), "recall_pct": _pct(recall),
        })

    supporting_rows = []
    for metric in supporting:
        if metric.get("metric_id") == "HOLDOUT-RECALL":
            continue
        supporting_rows.append({
            "id": metric.get("metric_id"),
            "label": metric.get("label", ""),
            "value_pct": _pct(metric.get("value")),
            "fraction": _fraction(metric),
        })

    holdout_view = None
    if holdout:
        holdout_view = {
            "value_pct": _pct(holdout.get("value")),
            "fraction": _fraction(holdout),
            "interval_text": (
                f"95% Wilson interval {_pct(holdout.get('interval_low'))}–{_pct(holdout.get('interval_high'))}"
                if holdout.get("interval_low") is not None else "No interval reported"
            ),
            "fixture_id": holdout.get("fixture_id") or "northstar-pc-2026.10",
            "caveat": holdout.get("caveat", "Pre-computed holdout aggregate; not imported."),
        }

    return {
        "facts": facts,
        "chart_rows": chart_rows,
        "bar_rows": bar_rows,
        "baseline_rows": baseline_rows,
        "margin_rows": margin_rows,
        "per_rule_rows": per_rule_rows,
        "supporting_rows": supporting_rows,
        "holdout": holdout_view,
        "m6_counts": m6_counts,
        "m5_top8": (
            {"fraction": _fraction(top8), "pct": _pct(top8.get("value")),
             "aria": _metric_aria(top8)}
            if top8 else None
        ),
        "baseline_footnote": (
            "The pre-registered always-answer assistant refusal-recall baseline (0.0%) "
            "is not a meaningful comparator for this demo and is omitted from the table."
        ),
    }


def _fallback_spine(feature: dict[str, Any], evidence_by_id: dict[str, Any]) -> Spine:
    """Build an inventory spine from evidence for runs predating multi-spine output."""
    nodes: list[SpineNode] = []
    seen: set[str] = set()
    for evidence_id in feature.get("evidence_ids", []):
        item = evidence_by_id.get(evidence_id)
        if not item:
            continue
        path = item.get("path", "")
        if not path or path in seen:
            continue
        seen.add(path)
        lower = path.lower()
        if "/gtest/" in lower or lower.startswith("gtest/"):
            kind = "test"
        elif lower.endswith(".gs"):
            kind = "symbol"
        elif lower.startswith("config/integration/"):
            kind = "config"
        else:
            kind = "artifact"
        nodes.append(SpineNode(
            id=f"evidence:{path}",
            kind=kind,
            label=Path(path).stem.replace("PersonalVehicle", "Vehicle").replace("PersonalAuto", "Auto"),
            artifact_path=path,
            evidence_id=evidence_id,
            confidence=Confidence(item.get("confidence", "linked")),
        ))
    return Spine(nodes=nodes, edges=[])


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
    migration = _read(store, run_id, "migration.json", None)

    evidence_by_id = {item["evidence_id"]: item for item in evidence + review_evidence}
    selected_feature = features[0] if features else None
    spines = dict(spine_payload.get("spines", {}))
    for feature in features:
        if feature["feature_id"] not in spines:
            spines[feature["feature_id"]] = _fallback_spine(feature, evidence_by_id).model_dump(mode="json")
    selected_spine = None
    if selected_feature:
        selected_spine = spines.get(selected_feature["feature_id"])

    view = {
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
        "migration": migration,
        "spines": spines,
        "selected_feature": selected_feature,
        "selected_spine": selected_spine,
        "spine_layout": spine_layout(selected_spine),
        "unsupported_count": len(manifest.get("unsupported_paths", [])),
        "precision_guards": PRECISION_GUARDS,
    }
    view["feature_summary"] = feature_summary(view)
    view["evaluation"] = evaluation_view(view)
    return view
