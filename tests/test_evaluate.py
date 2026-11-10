"""Evaluation tests: six headline metrics, denominators, baselines, caveats.

Written before app/services/evaluate.py exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.compare import compare_feature
from app.services.discovery import run_discovery
from app.services.evaluate import evaluate_run
from app.services.intake import build_manifest
from app.services.reconstruction import reconstruct
from app.services.review import run_review
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"
GROUND = REPO / "ground_truth"


@pytest.fixture(scope="module")
def evaluation(tmp_path_factory):
    manifest = build_manifest(DEMO, snapshot_id="S-DEMO", project_id="P-DEMO")
    discovery = run_discovery(DEMO, manifest)
    store = RunStore(tmp_path_factory.mktemp("data"))
    store.create_run("R-TEST")
    reconstruction = reconstruct(DEMO, manifest, discovery, "PA-VEH-01",
                                 store=store, run_id="R-TEST",
                                 draft_root=store.run_dir("R-TEST") / "draft")
    review = run_review(DEMO, manifest, discovery, include_thesis=False)
    reference = json.loads((GROUND / "reference_target" / "pa_veh_01_reference.json").read_text(encoding="utf-8"))
    comparison = compare_feature(reference, reconstruction.mappings, discovery.evidence)
    result = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=reconstruction, review=review, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo",
    )
    return manifest, discovery, reconstruction, review, comparison, result


def test_six_primary_metrics(evaluation) -> None:
    *_, result = evaluation
    primary = [m for m in result.metrics if m.primary]
    assert [m.metric_id for m in primary] == ["M1", "M2", "M3", "M4", "M5", "M6"]
    for metric in primary:
        assert metric.denominator > 0
        assert 0.0 <= metric.value <= 1.0
        assert metric.caveat
        assert metric.fixture_id == "demo-slice-300"
        assert metric.tier == "demo"


def test_demo_tier_counts(evaluation) -> None:
    *_, result = evaluation
    by_id = {m.metric_id: m for m in result.metrics}
    assert (by_id["M1"].numerator, by_id["M1"].denominator) == (8, 8)
    assert (by_id["M2"].numerator, by_id["M2"].denominator) == (8, 8)
    assert (by_id["M3"].numerator, by_id["M3"].denominator) == (101, 101)
    sample = next(m for m in result.supporting if m.metric_id == "M3-SAMPLE")
    assert (sample.numerator, sample.denominator) == (30, 30)
    assert (by_id["M4"].numerator, by_id["M4"].denominator) == (12, 12)
    assert (by_id["M5"].numerator, by_id["M5"].denominator) == (6, 6)
    assert by_id["M6"].value == pytest.approx(1.0)
    assert (by_id["M6"].numerator, by_id["M6"].denominator) == (48, 48)


def test_silent_omission_is_zero(evaluation) -> None:
    *_, result = evaluation
    metric = next(m for m in result.supporting if m.metric_id == "SILENT-OMISSION")
    assert metric.numerator == 0
    assert metric.value == 0.0


def test_baselines_are_reported_and_lower(evaluation) -> None:
    *_, result = evaluation
    assert set(result.baselines) >= {
        "identity_mapper", "all_unresolved", "pcf_grep_discovery", "grep_only_findings",
    }
    by_id = {m.metric_id: m for m in result.metrics}
    assert result.baselines["identity_mapper"] <= by_id["M4"].value
    assert result.baselines["all_unresolved"] == 0.0


def test_per_rule_table(evaluation) -> None:
    *_, result = evaluation
    assert len(result.per_rule) == 8
    for rule_id, stats in result.per_rule.items():
        assert stats["tp"] == 3
        assert stats["fp"] == 0
        assert stats["fn"] == 0


def test_no_generalisation_claim(evaluation) -> None:
    *_, result = evaluation
    caveats = " ".join(m.caveat.lower() for m in result.metrics)
    assert "synthetic" in caveats
    assert "not a benchmark" in caveats or "not generalis" in caveats


def test_evidence_audit_rejects_a_fabricated_excerpt(evaluation) -> None:
    from app.models import Confidence, Locator, LocatorKind, make_evidence
    from app.services.evaluate import audit_evidence_support

    manifest, discovery, reconstruction, review, comparison, result = evaluation
    ev = make_evidence(
        evidence_id="EV-FAKE", path="config/metadata/entity/PersonalVehicle.eti",
        locator=Locator(kind=LocatorKind.XPATH, value="/entity/column[1]", line=3),
        excerpt="THIS EXCERPT DOES NOT EXIST", method="xml_xpath",
        confidence=Confidence.PARSED,
    )
    assert audit_evidence_support(DEMO, ev) is False


def test_wrong_disposition_lowers_m4(evaluation) -> None:
    from app.models import Disposition

    manifest, discovery, reconstruction, review, comparison, result = evaluation
    import copy

    bad = copy.deepcopy(reconstruction)
    bad.mappings[0].disposition = Disposition.UNRESOLVED_GAP
    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=bad, review=review, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo",
    )
    assert changed.metrics[3].value < result.metrics[3].value


def test_extra_mapping_lowers_m4(evaluation) -> None:
    from app.models import Confidence, Disposition, Mapping, Provenance

    manifest, discovery, reconstruction, review, comparison, result = evaluation
    import copy

    bad = copy.deepcopy(reconstruction)
    bad.mappings.append(Mapping(
        mapping_id="M-99", source_ref="Bogus.Field", source_name="Field",
        source_layer="installed_entity", target_path="schema.bogus", target_name="bogus",
        disposition=Disposition.MAPPED_EXACT, rule_id="R-BOGUS", provenance=Provenance.PREFLIGHT_CONVENTION,
        confidence=Confidence.LINKED, rationale="adversarial extra mapping",
    ))
    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=bad, review=review, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo",
    )
    assert changed.metrics[3].value < result.metrics[3].value


def test_missing_estimate_moving_finding_lowers_m5(evaluation) -> None:
    manifest, discovery, reconstruction, review, comparison, result = evaluation
    import copy

    fewer = copy.deepcopy(review)
    fewer.findings = [f for f in fewer.findings if f.rule_id != "PF-GW-NAM-001"]
    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=reconstruction, review=fewer, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo",
    )
    assert changed.metrics[4].value < result.metrics[4].value


def test_bogus_feature_lowers_m2(evaluation) -> None:
    manifest, discovery, reconstruction, review, comparison, result = evaluation
    import copy

    from app.models import Feature

    bad = copy.deepcopy(discovery)
    gosu_evidence = next(e for e in discovery.evidence if e.path.endswith(".gs"))
    bad.features = list(discovery.features) + [
        Feature(
            feature_id="BOGUS-01", capability="vehicle_information", name="Bogus Vehicle",
            lob="PersonalAuto", description="wrong anchor", evidence_ids=[gosu_evidence.evidence_id],
            dependencies=[], confidence="parsed", open_questions=[],
        )
    ]
    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=bad,
        reconstruction=reconstruction, review=review, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo",
    )
    assert changed.metrics[1].value < result.metrics[1].value


def test_wrong_source_lowers_m4(evaluation) -> None:
    import copy

    manifest, discovery, reconstruction, review, comparison, result = evaluation
    bad = copy.deepcopy(reconstruction)
    bad.mappings[0].source_ref = "Totally.Wrong.Source"
    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=bad, review=review, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo",
    )
    assert changed.metrics[3].value < result.metrics[3].value


def test_duplicate_mapping_lowers_m4(evaluation) -> None:
    import copy

    manifest, discovery, reconstruction, review, comparison, result = evaluation
    bad = copy.deepcopy(reconstruction)
    bad.mappings.append(copy.deepcopy(bad.mappings[0]))
    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=bad, review=review, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo",
    )
    assert changed.metrics[3].value < result.metrics[3].value
