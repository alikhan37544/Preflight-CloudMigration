"""Discovery tests: candidate assembly, evidence, confidence, gaps, spine.

Written before app/services/discovery.py exists. Uses the generated 300-file
demo slice, which is feature-complete for PA-VEH-01.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.discovery import run_discovery
from app.services.intake import build_manifest
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"
HOLDOUT = REPO / "fixtures" / "northstar-pc-2026.10"


@pytest.fixture(scope="module")
def demo_manifest():
    return build_manifest(DEMO, snapshot_id="S-DEMO", project_id="P-DEMO")


@pytest.fixture(scope="module")
def discovery(demo_manifest):
    return run_discovery(DEMO, demo_manifest)


def test_discovers_eight_demo_features(discovery) -> None:
    ids = [f.feature_id for f in discovery.features]
    assert ids == [
        "PA-VEH-01", "PA-VEH-02", "PA-DRV-01", "PA-DRV-02",
        "PA-COV-01", "PA-COV-02", "PA-POL-01", "PA-POL-02",
    ]
    assert len(discovery.features) == 8


def test_every_feature_has_resolvable_evidence(discovery, demo_manifest) -> None:
    evidence_by_id = {e.evidence_id: e for e in discovery.evidence}
    assert len(evidence_by_id) == len(discovery.evidence)
    for feature in discovery.features:
        assert feature.evidence_ids, feature.feature_id
        for evidence_id in feature.evidence_ids:
            ev = evidence_by_id[evidence_id]
            path = DEMO / ev.path
            assert path.is_file(), (feature.feature_id, ev.path)
            if ev.locator.line:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                assert 1 <= ev.locator.line <= len(lines) + 1
            assert hashlib.sha256(ev.excerpt.encode("utf-8")).hexdigest() == ev.excerpt_sha


def test_pa_veh_01_cross_artefact_evidence(discovery) -> None:
    feature = next(f for f in discovery.features if f.feature_id == "PA-VEH-01")
    evidence_by_id = {e.evidence_id: e for e in discovery.evidence}
    paths = {evidence_by_id[eid].path for eid in feature.evidence_ids}
    assert "config/web/pcf/policy/PAVehicleDV.pcf" in paths
    assert "config/metadata/entity/PersonalVehicle.eti" in paths
    assert "config/extensions/entity/PersonalVehicle.etx" in paths
    assert "config/metadata/typelist/VehicleType.tti" in paths
    assert "config/extensions/typelist/VehicleType.ttx" in paths
    assert "product/template/PersonalAutoTemplate.xml" in paths
    assert "gsrc/acme/validation/PersonalVehicleValidation.gs" in paths
    assert "gtest/acme/PersonalVehicleValidationTest.gs" in paths
    assert "gtest/acme/PersonalVehicleRatingDBTest.gs" in paths
    assert feature.capability == "vehicle_information"


def test_confidence_is_earned_not_assumed(discovery) -> None:
    feature = next(f for f in discovery.features if f.feature_id == "PA-VEH-01")
    evidence_by_id = {e.evidence_id: e for e in discovery.evidence}
    parsed = [evidence_by_id[e] for e in feature.evidence_ids if evidence_by_id[e].confidence.value == "parsed"]
    assert parsed, "at least one parsed anchor"
    for ev in parsed:
        assert ev.method in {"xml_xpath", "lexer"}


def test_territory_gap_is_explicit(discovery) -> None:
    kinds = {(gap.kind.value, gap.subject) for gap in discovery.gaps}
    assert ("missing_source", "territory") in kinds
    assert any(gap.kind.value == "unsupported" and "rating" in gap.subject for gap in discovery.gaps)
    assert any(gap.kind.value == "ambiguous_reference" for gap in discovery.gaps)


def test_source_spine_has_cross_artefact_edges(discovery) -> None:
    spine = discovery.spines["PA-VEH-01"]
    node_kinds = {node.kind for node in spine.nodes}
    assert {"feature", "artifact", "test"} <= node_kinds
    edge_kinds = {edge.kind for edge in spine.edges}
    assert {"references", "tested_by"} <= edge_kinds
    assert len(spine.edges) == 7
    assert sum(1 for e in spine.edges if e.kind == "tested_by") == 2


def test_holdout_naming_shift_discovers_four_features() -> None:
    manifest = build_manifest(HOLDOUT, snapshot_id="S-H", project_id="P-H")
    result = run_discovery(HOLDOUT, manifest)
    capabilities = {f.capability for f in result.features}
    assert capabilities == {
        "vehicle_information", "driver_information",
        "coverage_selection", "policy_questions",
    }
    assert len(result.features) == 4


def test_discovery_does_not_emit_noise_features(discovery) -> None:
    for feature in discovery.features:
        assert not feature.feature_id.startswith("GEN")
        assert feature.evidence_ids
