"""Contract tests for the PreFlight data model.

These tests are written before the implementation. They pin the enums,
required fields, cross-field validation, and JSON round-tripping that the
rest of the product depends on.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.models import (
    SCHEMA_VERSION,
    Artifact,
    ArtifactStatus,
    Assumption,
    AuditEvent,
    Change,
    ClaimStrength,
    ComparisonClass,
    ComparisonRow,
    Confidence,
    Decision,
    DecisionAction,
    Disposition,
    Evidence,
    Feature,
    Finding,
    Gap,
    GapKind,
    Locator,
    LocatorKind,
    Mapping,
    Metric,
    Provenance,
    Run,
    RunStatus,
    Severity,
    Snapshot,
    Spine,
    SpineEdge,
    SpineNode,
    StandardFamily,
    make_evidence,
)


HEX = "a" * 64


def evidence(**overrides) -> Evidence:
    data = dict(
        evidence_id="EV-1",
        path="config/metadata/entity/PersonalVehicle.eti",
        locator=Locator(kind=LocatorKind.XPATH, value="/entity/column[1]", line=3),
        excerpt="<column name=\"ModelYear\" type=\"Integer\"/>",
        excerpt_sha=HEX,
        method="xml_xpath",
        confidence=Confidence.PARSED,
    )
    data.update(overrides)
    return Evidence(**data)


def test_schema_version_is_stable() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert evidence().schema_version == "1.0"


def test_enums_match_contract() -> None:
    assert {c.value for c in ArtifactStatus} == {
        "parsed", "partial", "unsupported", "binary", "corrupt", "excluded"
    }
    assert {c.value for c in Confidence} == {
        "parsed", "linked", "inferred-review", "unresolved"
    }
    assert {c.value for c in Disposition} == {
        "mapped_exact", "mapped_transformed", "intentionally_dropped",
        "not_applicable", "unresolved_gap", "unsupported",
    }
    assert {c.value for c in Provenance} == {
        "guidewire-doc", "preflight-convention", "reviewer-decision"
    }
    assert {c.value for c in ClaimStrength} == {
        "verified-id", "verified-policy", "verified-doc", "secondary", "heuristic"
    }
    assert {c.value for c in StandardFamily} == {
        "cloud-standard", "gosu-secure-coding", "hardening-guidance",
        "internal-guidance", "none",
    }
    assert {c.value for c in ComparisonClass} == {
        "preserved", "changed", "missing", "added", "unresolved"
    }
    assert {c.value for c in GapKind} == {
        "missing_source", "missing_target", "ambiguous_reference", "unsupported"
    }
    assert {c.value for c in RunStatus} == {
        "queued", "running", "succeeded", "failed", "cancelled"
    }
    assert {c.value for c in Severity} == {"error", "warning", "note", "info"}
    assert {c.value for c in DecisionAction} == {"accept", "reject", "edit", "defer"}


def test_locator_requires_value_and_valid_line() -> None:
    assert Locator(kind=LocatorKind.JSON_POINTER, value="/properties/modelYear").value
    with pytest.raises(ValidationError):
        Locator(kind=LocatorKind.LINE, value="")
    with pytest.raises(ValidationError):
        Locator(kind=LocatorKind.XPATH, value="/a", line=0)


def test_evidence_rejects_short_or_non_hex_digest() -> None:
    with pytest.raises(ValidationError):
        evidence(excerpt_sha="abc")
    with pytest.raises(ValidationError):
        evidence(excerpt_sha="z" * 64)


def test_make_evidence_fingerprints_excerpt() -> None:
    ev = make_evidence(
        evidence_id="EV-2",
        path="config/web/pcf/policy/PAVehicleDV.pcf",
        locator=Locator(kind=LocatorKind.XPATH, value="/PCF/Screen/TextInput[1]", line=4),
        excerpt="<TextInput id=\"ModelYear\"/>",
        method="xml_xpath",
        confidence=Confidence.PARSED,
    )
    assert len(ev.excerpt_sha) == 64
    assert ev.excerpt_sha != ev.excerpt


def test_feature_requires_an_anchor_evidence_id() -> None:
    with pytest.raises(ValidationError):
        Feature(
            feature_id="PA-VEH-01", name="Vehicle", lob="PersonalAuto",
            description="Vehicle information", evidence_ids=[], dependencies=[],
            confidence=Confidence.PARSED, open_questions=[],
        )


def test_mapping_guidewire_doc_requires_source_and_quote() -> None:
    with pytest.raises(ValidationError):
        Mapping(
            mapping_id="M-1", source_ref="PAVehicle", source_name="PAVehicle",
            source_layer="apd_template", target_path="codegen",
            target_name="PersonalVehicle", disposition=Disposition.MAPPED_TRANSFORMED,
            rule_id="R-CG-01", provenance=Provenance.GUIDEWIRE_DOC,
            confidence=Confidence.LINKED, rationale="documented",
        )
    ok = Mapping(
        mapping_id="M-1", source_ref="PAVehicle", source_name="PAVehicle",
        source_layer="apd_template", target_path="codegen",
        target_name="PersonalVehicle", disposition=Disposition.MAPPED_TRANSFORMED,
        rule_id="R-CG-01", provenance=Provenance.GUIDEWIRE_DOC,
        confidence=Confidence.LINKED, rationale="documented",
        source_url="https://docs.guidewire.com/example",
        quote="PAVehicle: nameOverride: PersonalVehicle",
    )
    assert ok.provenance is Provenance.GUIDEWIRE_DOC


def test_mapping_convention_requires_rationale() -> None:
    with pytest.raises(ValidationError):
        Mapping(
            mapping_id="M-2", source_ref="ModelYear", source_name="ModelYear",
            source_layer="installed_entity", target_path="schema", target_name="modelYear",
            disposition=Disposition.MAPPED_TRANSFORMED, rule_id="R-API-03",
            provenance=Provenance.PREFLIGHT_CONVENTION, confidence=Confidence.INFERRED_REVIEW,
            rationale="",
        )


def test_finding_claim_strength_constraints() -> None:
    common = dict(
        finding_id="F-1", rule_id="PF-GW-SQL-001", rule_version="1.0",
        title="Direct SQL", severity=Severity.ERROR, confidence=Confidence.PARSED,
        evidence_ids=["EV-1"], message="m", remediation="r",
    )
    with pytest.raises(ValidationError):
        Finding(claim_strength=ClaimStrength.VERIFIED_ID, standard_family=StandardFamily.CLOUD_STANDARD, **common)
    with pytest.raises(ValidationError):
        Finding(claim_strength=ClaimStrength.HEURISTIC, standard_id="IS-TLS-1238",
                standard_family=StandardFamily.NONE, **common)
    ok = Finding(
        claim_strength=ClaimStrength.VERIFIED_ID, standard_family=StandardFamily.CLOUD_STANDARD,
        standard_id="IS-TLS-1238", standard_title="Use of Direct SQL Calls",
        standard_url="https://docs.guidewire.com/example", access="gated-body", **common,
    )
    assert ok.standard_id == "IS-TLS-1238"


def test_assumption_impact_range_ordering() -> None:
    with pytest.raises(ValidationError):
        Assumption(
            assumption_id="A-1", statement="territory unknown", impact="high",
            impact_range_days=(9, 7), impact_basis="formula", impact_confidence="low",
            impact_caveat="heuristic", status="open", owner="unassigned",
            question_to_ask="Where?", related_mapping_id="M-1", gap_id="G-1",
        )


def test_metric_denominator_and_bounds() -> None:
    with pytest.raises(ValidationError):
        Metric(metric_id="M1", label="recall", numerator=1, denominator=0, unit="ratio", caveat="c", fixture_id="f", tier="demo", primary=True)
    with pytest.raises(ValidationError):
        Metric(metric_id="M1", label="recall", numerator=2, denominator=1, unit="ratio", caveat="c", fixture_id="f", tier="demo", primary=True)
    m = Metric(metric_id="M1", label="recall", numerator=3, denominator=4, unit="ratio", caveat="c", fixture_id="f", tier="demo", primary=True)
    assert m.value == pytest.approx(0.75)


def test_audit_event_genesis_and_roundtrip() -> None:
    ev = AuditEvent(
        event_id="AE-1", run_id="R-1", seq=0, ts="2026-11-07T00:00:00Z",
        actor="system", action="run.created", object_type="run", object_id="R-1",
        before_hash=None, after_hash=HEX, prev_hash="GENESIS", hash=HEX,
    )
    restored = AuditEvent.model_validate_json(ev.model_dump_json())
    assert restored == ev


def test_run_lifecycle_and_progress() -> None:
    run = Run(
        run_id="R-1", project_id="P-1", snapshot_id="S-1", status=RunStatus.QUEUED,
        stage="queued", progress={"stage": "queued", "files_done": 0, "files_total": 10, "percent": 0},
        release_context="Qusar 2026.08", parser_version="1.0", rulepack_version="1.0",
        created_at="2026-11-07T00:00:00Z",
    )
    assert run.status is RunStatus.QUEUED
    assert run.progress.percent == 0


def test_snapshot_requires_hash_and_synthetic_flag() -> None:
    snap = Snapshot(
        snapshot_id="S-1", project_id="P-1", root="fixtures/acme", sha256=HEX,
        file_count=3, size_bytes=100, created_at="2026-11-07T00:00:00Z", synthetic=True,
    )
    assert snap.synthetic is True
    with pytest.raises(ValidationError):
        Snapshot(snapshot_id="S-2", project_id="P-1", root="x", sha256="bad",
                 file_count=1, size_bytes=1, created_at="2026-11-07T00:00:00Z", synthetic=True)


def test_spine_edges_must_reference_nodes() -> None:
    with pytest.raises(ValidationError):
        Spine(
            nodes=[SpineNode(id="n1", kind="feature", label="Vehicle", confidence=Confidence.PARSED)],
            edges=[SpineEdge(id="e1", src="n1", dst="n2", kind="references", confidence=Confidence.LINKED)],
        )


def test_artifact_status_and_line_count() -> None:
    a = Artifact(
        path="a.pcf", sha256=HEX, size=10, kind="pcf", parser="pcf",
        status=ArtifactStatus.PARSED, warnings=[], line_count=2,
    )
    assert a.status is ArtifactStatus.PARSED
    with pytest.raises(ValidationError):
        Artifact(path="a", sha256="nope", size=1, kind="pcf", parser="pcf",
                 status=ArtifactStatus.PARSED, warnings=[], line_count=1)


def test_gap_and_decision_roundtrip() -> None:
    gap = Gap(
        gap_id="G-1", kind=GapKind.MISSING_SOURCE, subject="territory",
        evidence_sought="rating table", impact="high", owner="unassigned",
        status="open", assumption_id="A-1",
    )
    assert json.loads(gap.model_dump_json())["kind"] == "missing_source"
    d = Decision(
        decision_id="D-1", object_type="mapping", object_id="M-1",
        action=DecisionAction.ACCEPT, actor="reviewer",
        reason="Verified against docs", before_hash=HEX, after_hash=HEX,
        created_at="2026-11-07T00:00:00Z",
    )
    assert d.action is DecisionAction.ACCEPT


def test_change_starts_pending_and_requires_edit_reason() -> None:
    change = Change(
        change_id="C-1", target_path="draft/x.yaml", diff="+a: b", mapping_id="M-1",
        approval_state="pending",
    )
    assert change.approval_state == "pending"
    with pytest.raises(ValidationError):
        Change(
            change_id="C-2", target_path="draft/x.yaml", diff="+a: b", mapping_id="M-1",
            approval_state="edited", edited_value="b", previous_value="a", edit_reason="",
        )


def test_comparison_row_missing_requires_complete_scope() -> None:
    with pytest.raises(ValidationError):
        ComparisonRow(
            row_id="CR-1", source_ref="territory", target_ref=None,
            **{"class": ComparisonClass.MISSING}, evidence_ids=[],
            rationale="no target", confidence=Confidence.UNRESOLVED,
            target_scope_complete=False,
        )
