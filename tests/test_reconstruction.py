"""Reconstruction tests: 12 mappings, drafts, assumptions, spine invariants.

Written before app/services/reconstruction.py exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.discovery import run_discovery
from app.services.intake import build_manifest, snapshot_hash
from app.services.reconstruction import (
    DRAFT_FILES,
    reconstruct,
    validate_draft_directory,
)
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"


@pytest.fixture(scope="module")
def demo_manifest():
    return build_manifest(DEMO, snapshot_id="S-DEMO", project_id="P-DEMO")


@pytest.fixture(scope="module")
def discovery(demo_manifest):
    return run_discovery(DEMO, demo_manifest)


@pytest.fixture(scope="module")
def reconstruction(demo_manifest, discovery, tmp_path_factory):
    store = RunStore(tmp_path_factory.mktemp("data"))
    store.create_run("R-TEST")
    return reconstruct(
        DEMO, demo_manifest, discovery, "PA-VEH-01",
        store=store, run_id="R-TEST", draft_root=store.run_dir("R-TEST") / "draft",
    )


def test_installed_driver_entity_matches_codegen_override(demo_manifest, discovery, reconstruction) -> None:
    driver_feature = next(f for f in discovery.features if f.feature_id == "PA-DRV-01")
    evidence_by_id = {e.evidence_id: e for e in discovery.evidence}
    driver_paths = {evidence_by_id[eid].path for eid in driver_feature.evidence_ids}
    assert "config/metadata/entity/VehicleDriver.eti" in driver_paths
    assert "config/extensions/entity/VehicleDriver.etx" in driver_paths
    assert not any("PersonalVehicleDriver" in path for path in driver_paths)
    driver_mapping = next(m for m in reconstruction.mappings if m.rule_id == "R-CG-03")
    assert driver_mapping.target_name == "VehicleDriver"
    assert (DEMO / "config/metadata/entity/VehicleDriver.eti").is_file()


def test_twelve_explicit_mappings(reconstruction) -> None:
    rules = [m.rule_id for m in reconstruction.mappings]
    assert rules == [
        "R-CG-01", "R-CG-02", "R-CG-03", "R-CG-04", "R-GW-24-01",
        "R-API-01", "R-API-02", "R-API-03", "R-API-04", "R-API-05", "R-API-06",
        "R-TYP-01",
    ]
    assert all(m.disposition.value for m in reconstruction.mappings)


def test_guidewire_doc_mappings_carry_a_url_and_quote(reconstruction) -> None:
    documented = [m for m in reconstruction.mappings if m.provenance.value == "guidewire-doc"]
    assert len(documented) == 5
    for mapping in documented:
        assert mapping.source_url and mapping.source_url.startswith("https://")
        assert mapping.quote and len(mapping.quote) > 10


def test_every_source_property_has_an_explicit_disposition(reconstruction) -> None:
    expected_sources = {
        "PersonalVehicle.ModelYear", "PersonalVehicle.Make", "PersonalVehicle.VIN",
        "PersonalVehicle.Usage", "PersonalVehicle.VehicleType",
        "PersonalVehicle.GarageLocation_Ext", "VehicleType.Motorcycle_Ext",
        "PAVehicle", "PAVehicle.Year", "PADriver", "PALine",
        "PersonalAutoRatingFactorConfiguration",
    }
    covered = {m.source_ref for m in reconstruction.mappings}
    assert covered == expected_sources
    assert reconstruction.silent_omissions == []


def test_assumptions_are_impact_rated(reconstruction) -> None:
    statements = " ".join(a.statement.lower() for a in reconstruction.assumptions)
    assert "territory" in statements
    assert "rating" in statements
    long_type = next(a for a in reconstruction.assumptions if "24" in a.statement or "long type" in a.statement.lower())
    assert long_type.impact_range_days == (7.0, 9.0)
    assert "two files" in long_type.impact_basis.lower()
    assert "0 tests" in long_type.impact_basis.lower()
    assert "heuristic" in long_type.impact_basis.lower()
    assert "11" not in long_type.impact_basis
    assert "PA-VEH-02" in long_type.statement
    assert "product/template/LongTypeA.xml" in long_type.statement
    assert "config/resources/productmodel/PersonalAuto.xml" in long_type.statement
    assert "template and product-model change" in long_type.question_to_ask
    assert "not a quote" in long_type.impact_caveat.lower()
    assert all(a.status == "open" for a in reconstruction.assumptions)


def test_draft_files_exist_and_no_generated_files(reconstruction) -> None:
    for rel in DRAFT_FILES:
        assert (reconstruction.draft_root / rel).is_file(), rel
    assert not list(reconstruction.draft_root.rglob("*_gen*"))
    assert not (reconstruction.draft_root / "config/integration/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json_gen").exists()


def test_draft_validates_against_local_contract(reconstruction) -> None:
    assert reconstruction.validation_errors == []
    assert validate_draft_directory(reconstruction.draft_root) == []


def test_codegen_draft_contains_verified_overrides(reconstruction) -> None:
    import json
    import yaml

    path = reconstruction.draft_root / "config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    types = data["types"]
    assert types["PAVehicle"]["nameOverride"] == "PersonalVehicle"
    assert types["PAVehicle"]["fields"]["Year"]["nameOverride"] == "ModelYear"
    # The APD template field is GarageLocation; the installed extension column
    # is GarageLocation_Ext. nameOverride bridges the two names.
    garage = types["PAVehicle"]["fields"]["GarageLocation"]
    assert garage["nameOverride"] == "GarageLocation_Ext"
    assert garage["requiredForCreate"] is False
    assert "GarageLocation_Ext" not in types["PAVehicle"]["fields"]
    assert types["PADriver"]["nameOverride"] == "VehicleDriver"
    assert types["PALine"]["nameOverride"] == "PersonalAutoLine"
    assert types["PersonalAutoRatingFactor"]["nameOverride"] == "PersonalAutoRatingFactorConfiguration"

    updater = json.loads(
        (reconstruction.draft_root / "config/integration/updaters/ext/policyperiod/v1/"
         "policyperiod_pa_ext-1.0.updater.json").read_text(encoding="utf-8")
    )
    assert updater["create"]["garageLocation"] == "GarageLocation_Ext"
    assert updater["update"]["garageLocation"] == "GarageLocation_Ext"
    assert updater["create"]["vehicleType"] == "VehicleType"


def test_codegen_schema_and_updater_agree_on_garage_location(reconstruction) -> None:
    import json
    import yaml

    codegen = yaml.safe_load((
        reconstruction.draft_root / "config/integration/apis/installedlobs/"
        "pa_codegen_config_ext-1.0.yaml"
    ).read_text(encoding="utf-8"))
    schema = json.loads((
        reconstruction.draft_root / "config/integration/schemas/ext/policyperiod/v1/"
        "policyperiod_pa_ext-1.0.schema.json"
    ).read_text(encoding="utf-8"))
    updater = json.loads((
        reconstruction.draft_root / "config/integration/updaters/ext/policyperiod/v1/"
        "policyperiod_pa_ext-1.0.updater.json"
    ).read_text(encoding="utf-8"))

    garage = codegen["types"]["PAVehicle"]["fields"]["GarageLocation"]
    assert garage["nameOverride"] == updater["create"]["garageLocation"]
    assert garage["nameOverride"] == updater["update"]["garageLocation"]
    # requiredForCreate false => the API property is optional in the schema.
    assert garage["requiredForCreate"] is False
    assert "garageLocation" not in schema["required"]
    assert "garageLocation" in schema["properties"]


def test_schema_draft_has_expected_properties(reconstruction) -> None:
    import json

    path = reconstruction.draft_root / "config/integration/schemas/ext/policyperiod/v1/policyperiod_pa_ext-1.0.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    assert schema["$id"] == "preflight-target-v1"
    assert set(schema["properties"]) >= {
        "modelYear", "make", "vin", "usage", "vehicleType", "garageLocation"
    }
    assert "garageLocation" not in schema["required"]
    assert set(schema["required"]) == {
        "modelYear", "make", "vin", "usage", "vehicleType"
    }
    assert "motorcycle" in schema["properties"]["vehicleType"]["enum"]


def test_all_changes_start_pending(reconstruction) -> None:
    assert reconstruction.changes
    assert all(change.approval_state == "pending" for change in reconstruction.changes)
    assert reconstruction.patch_diff
    assert "nameOverride: PersonalVehicle" in reconstruction.patch_diff


def test_source_snapshot_unchanged(demo_manifest, reconstruction) -> None:
    assert snapshot_hash(DEMO) == demo_manifest.sha256


def test_spine_hits_pa_veh_01_invariants(reconstruction) -> None:
    spine = reconstruction.spines["PA-VEH-01"]
    references = [e for e in spine.edges if e.kind != "tested_by"]
    tests = [e for e in spine.edges if e.kind == "tested_by"]
    assert len(references) == 11
    assert len(tests) == 2

    kinds = set()
    for node in spine.nodes:
        if node.artifact_path and node.artifact_path.endswith(".pcf"):
            kinds.add("pcf")
        elif node.artifact_path and node.artifact_path.endswith((".eti", ".etx")):
            kinds.add("entity")
        elif node.artifact_path and node.artifact_path.endswith((".tti", ".ttx")):
            kinds.add("typelist")
        elif node.artifact_path and ("template" in node.artifact_path or "codegen" in node.artifact_path):
            kinds.add("template_codegen")
    assert kinds == {"pcf", "entity", "typelist", "template_codegen"}


def test_mapping_rules_are_loaded_from_the_rule_pack() -> None:
    import yaml

    from app.services.reconstruction import _build_mappings

    payload = yaml.safe_load((REPO / "rules" / "mapping_rules.yaml").read_text(encoding="utf-8"))
    expected = [row for row in payload["rules"] if row.get("emitted", True)]
    mappings = _build_mappings()
    assert len(mappings) == len(expected) == 12
    for mapping, row in zip(mappings, expected):
        assert mapping.rule_id == row["rule_id"]
        assert mapping.source_ref == row["source"]
        assert mapping.target_path == row["target"]
        assert mapping.target_name == row["target_name"]
        assert mapping.disposition.value == row["disposition"]
