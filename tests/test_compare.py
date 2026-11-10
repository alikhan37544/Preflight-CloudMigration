"""Comparison tests: five classes, no false missing, reference-target agreement.

Written before app/services/compare.py exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.compare import compare_feature
from app.services.discovery import run_discovery
from app.services.intake import build_manifest
from app.services.reconstruction import reconstruct
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"
REFERENCE = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"


@pytest.fixture(scope="module")
def context(tmp_path_factory):
    manifest = build_manifest(DEMO, snapshot_id="S-DEMO", project_id="P-DEMO")
    discovery = run_discovery(DEMO, manifest)
    store = RunStore(tmp_path_factory.mktemp("data"))
    store.create_run("R-TEST")
    reconstruction = reconstruct(DEMO, manifest, discovery, "PA-VEH-01",
                                 store=store, run_id="R-TEST",
                                 draft_root=store.run_dir("R-TEST") / "draft")
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return manifest, discovery, reconstruction, reference


def test_reference_comparison_has_expected_classes(context) -> None:
    _, discovery, reconstruction, reference = context
    result = compare_feature(
        reference, reconstruction.mappings, discovery.evidence,
        target_scope_complete=True,
    )
    by_source = {row.source_ref: row for row in result.rows}
    assert by_source["PersonalVehicle.ModelYear"].class_.value == "changed"
    assert by_source["PersonalVehicle.Make"].class_.value == "preserved"
    assert by_source["PersonalVehicle.VIN"].class_.value == "preserved"
    assert by_source["PersonalVehicle.Usage"].class_.value == "preserved"
    assert by_source["PersonalVehicle.VehicleType"].class_.value == "preserved"
    assert by_source["PersonalVehicle.GarageLocation_Ext"].class_.value == "changed"
    assert by_source["VehicleType.Motorcycle_Ext"].class_.value == "changed"
    assert by_source["PersonalVehicle.Territory_Ext"].class_.value == "unresolved"


def test_no_missing_without_complete_target_scope(context) -> None:
    _, discovery, reconstruction, reference = context
    result = compare_feature(
        reference, reconstruction.mappings, discovery.evidence,
        target_scope_complete=False,
    )
    assert all(row.class_.value != "missing" for row in result.rows)


def test_added_and_missing_are_unit_tested(context) -> None:
    _, discovery, reconstruction, _ = context
    synthetic = {
        "target_scope_complete": True,
        "properties": [
            {"source": "PersonalVehicle.Make", "target": "make", "class": "preserved"},
            {"source": "PersonalVehicle.Territory_Ext", "target": None, "class": "missing"},
            {"source": None, "target": "auditVersion", "class": "added"},
        ],
    }
    result = compare_feature(
        synthetic, reconstruction.mappings, discovery.evidence,
        target_scope_complete=True,
    )
    classes = {row.class_.value for row in result.rows}
    assert {"preserved", "missing", "added"} <= classes

    incomplete = compare_feature(
        synthetic, reconstruction.mappings, discovery.evidence,
        target_scope_complete=False,
    )
    missing_rows = [r for r in incomplete.rows if r.source_ref == "PersonalVehicle.Territory_Ext"]
    assert missing_rows and missing_rows[0].class_.value == "unresolved"


def test_reference_agreement_is_measured(context) -> None:
    _, discovery, reconstruction, reference = context
    result = compare_feature(reference, reconstruction.mappings, discovery.evidence)
    assert result.macro_f1 == pytest.approx(1.0)
    assert result.confusion["changed"]["changed"] == 3
    assert result.confusion["unresolved"]["unresolved"] == 1


def test_wrong_mapping_target_lowers_reference_f1(context) -> None:
    import copy

    _, discovery, reconstruction, reference = context
    wrong = copy.deepcopy(reconstruction.mappings)
    target = next(m for m in wrong if m.source_ref == "PersonalVehicle.ModelYear")
    target.target_name = "notModelYear"
    target.target_path = "schema.notModelYear"
    result = compare_feature(reference, wrong, discovery.evidence)
    assert result.macro_f1 < 1.0
    row = next(r for r in result.rows if r.source_ref == "PersonalVehicle.ModelYear")
    assert row.class_.value == "missing"



def test_every_source_row_links_evidence(context) -> None:
    _, discovery, reconstruction, reference = context
    result = compare_feature(reference, reconstruction.mappings, discovery.evidence)
    for row in result.rows:
        if row.source_ref:
            assert row.evidence_ids, row.source_ref


def test_reference_target_is_labelled_not_independent() -> None:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    assert reference["authored_blind"] is False
    assert "ai-assisted" in reference["independence"].lower()
    assert "not independent" in reference["independence"].lower()
