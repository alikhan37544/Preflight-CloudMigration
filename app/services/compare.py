"""Source-to-reference comparison with five explicit classes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.models import (
    ComparisonClass,
    ComparisonRow,
    Confidence,
    Evidence,
    Mapping,
)


@dataclass
class CompareResult:
    rows: list[ComparisonRow]
    macro_f1: float
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)


def _predicted_class(property_row: dict[str, Any], mapping: Mapping | None,
                     target_scope_complete: bool) -> ComparisonClass:
    source = property_row.get("source")
    target = property_row.get("target")
    if source is None and target:
        return ComparisonClass.ADDED
    if mapping is None:
        if target is None:
            row_scope = property_row.get("scope_complete", target_scope_complete)
            return ComparisonClass.MISSING if row_scope else ComparisonClass.UNRESOLVED
        return ComparisonClass.UNRESOLVED
    disposition = mapping.disposition.value
    if disposition == "mapped_exact":
        return ComparisonClass.PRESERVED
    if disposition == "mapped_transformed":
        return ComparisonClass.CHANGED
    if disposition in {"unresolved_gap", "unsupported"}:
        return ComparisonClass.UNRESOLVED
    if disposition in {"intentionally_dropped", "not_applicable"}:
        return ComparisonClass.MISSING if target_scope_complete else ComparisonClass.UNRESOLVED
    return ComparisonClass.UNRESOLVED


def _evidence_ids_for(source_ref: str | None, evidence: list[Evidence]) -> list[str]:
    if not source_ref:
        return []
    leaf = source_ref.rsplit(".", 1)[-1]
    matches = [ev.evidence_id for ev in evidence if leaf and leaf in ev.excerpt]
    return matches[:2]


def _f1(confusion: dict[str, dict[str, int]]) -> float:
    classes = [c.value for c in ComparisonClass]
    scores = []
    for cls in classes:
        tp = confusion.get(cls, {}).get(cls, 0)
        fn = sum(confusion.get(cls, {}).get(other, 0) for other in classes if other != cls)
        fp = sum(confusion.get(other, {}).get(cls, 0) for other in classes if other != cls)
        if tp + fn + fp == 0:
            continue
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        if precision + recall == 0:
            scores.append(0.0)
        else:
            scores.append(2 * precision * recall / (precision + recall))
    return sum(scores) / len(scores) if scores else 0.0


def compare_feature(reference: dict[str, Any], mappings: list[Mapping], evidence: list[Evidence],
                    *, target_scope_complete: bool | None = None) -> CompareResult:
    complete = bool(reference.get("target_scope_complete", True)) if target_scope_complete is None else target_scope_complete
    by_source = {mapping.source_ref: mapping for mapping in mappings}
    rows: list[ComparisonRow] = []
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for index, property_row in enumerate(reference.get("properties", []), start=1):
        source = property_row.get("source")
        target = property_row.get("target")
        expected = ComparisonClass(property_row.get("class", "unresolved"))
        mapping = by_source.get(source) if source else None
        predicted = _predicted_class(property_row, mapping, complete)
        confusion[expected.value][predicted.value] += 1
        rows.append(
            ComparisonRow(
                row_id=f"CR-{index:02d}",
                source_ref=source or "",
                target_ref=target,
                class_=predicted,
                evidence_ids=_evidence_ids_for(source, evidence),
                rationale=(
                    f"Reference expects '{expected.value}'; tool predicted '{predicted.value}' "
                    f"from rule {mapping.rule_id if mapping else 'none'}."
                ),
                confidence=Confidence.LINKED if mapping else Confidence.UNRESOLVED,
                target_scope_complete=complete,
            )
        )

    return CompareResult(rows=rows, macro_f1=_f1(confusion), confusion=dict(confusion))
