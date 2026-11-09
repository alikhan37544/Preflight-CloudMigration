"""Regression tests for evaluation-harness integrity holes.

These cover the snapshot-grounding, deduplication, locator, M5 denominator,
and false-positive gates rather than the happy-path demo scores.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from app.models import (
    Artifact,
    ArtifactStatus,
    Confidence,
    Locator,
    LocatorKind,
    Manifest,
    make_evidence,
)
from app.services.compare import CompareResult, compare_feature
from app.services.discovery import DiscoveryResult, run_discovery
from app.services.evaluate import (
    _mapping_grounded,
    _mapping_grounding_text,
    audit_evidence_support,
    evaluate_run,
)
from app.services.intake import build_manifest
from app.services.reconstruction import reconstruct
from app.services.review import ReviewResult, run_review
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"
GROUND = REPO / "ground_truth"


@pytest.fixture(scope="module")
def demo_eval(tmp_path_factory):
    manifest = build_manifest(DEMO, snapshot_id="S-DEMO", project_id="P-DEMO")
    discovery = run_discovery(DEMO, manifest)
    store = RunStore(tmp_path_factory.mktemp("eval-integrity"))
    store.create_run("R-INTEGRITY")
    reconstruction = reconstruct(
        DEMO, manifest, discovery, "PA-VEH-01",
        store=store, run_id="R-INTEGRITY",
        draft_root=store.run_dir("R-INTEGRITY") / "draft",
    )
    review = run_review(DEMO, manifest, discovery, include_thesis=False)
    reference = json.loads(
        (GROUND / "reference_target" / "pa_veh_01_reference.json").read_text(encoding="utf-8")
    )
    comparison = compare_feature(reference, reconstruction.mappings, discovery.evidence)
    result = evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=reconstruction, review=review, comparison=comparison,
        ground_truth_dir=GROUND, tier="demo", fixture_root=DEMO,
    )
    return manifest, discovery, reconstruction, review, comparison, result


def _evaluate(manifest, discovery, reconstruction, review, comparison,
              ground_truth_dir: Path = GROUND):
    return evaluate_run(
        fixture_id="demo-slice-300", manifest=manifest, discovery=discovery,
        reconstruction=reconstruction, review=review, comparison=comparison,
        ground_truth_dir=ground_truth_dir, tier="demo", fixture_root=DEMO,
    )


def _empty_manifest() -> Manifest:
    return Manifest(
        snapshot_id="S-EMPTY", project_id="P-EMPTY", sha256="0" * 64,
        artifacts=[], file_count=0, total_size=0,
    )


def _ground_truth_with_issues(tmp_path: Path, issues: list[dict]) -> Path:
    target = tmp_path / "ground_truth"
    shutil.copytree(GROUND, target)
    path = target / "estimate_moving_issues.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["issues"] = issues
    path.write_text(json.dumps(payload), encoding="utf-8")
    return target


def test_demo_headline_metrics_remain_full(demo_eval) -> None:
    *_, result = demo_eval
    by_id = {metric.metric_id: metric for metric in result.metrics}
    assert (by_id["M1"].numerator, by_id["M1"].denominator) == (8, 8)
    assert (by_id["M2"].numerator, by_id["M2"].denominator) == (8, 8)
    assert (by_id["M3"].numerator, by_id["M3"].denominator) == (101, 101)
    sample = next(metric for metric in result.supporting if metric.metric_id == "M3-SAMPLE")
    assert (sample.numerator, sample.denominator) == (30, 30)
    assert (by_id["M4"].numerator, by_id["M4"].denominator) == (12, 12)
    assert (by_id["M5"].numerator, by_id["M5"].denominator) == (6, 6)
    assert (by_id["M6"].numerator, by_id["M6"].denominator) == (48, 48)


def test_empty_snapshot_scores_zero_and_m4_is_not_static(demo_eval) -> None:
    _, _, reconstruction, _, _, _ = demo_eval
    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=_empty_manifest(),
        discovery=DiscoveryResult(), reconstruction=reconstruction,
        review=ReviewResult(), comparison=CompareResult(rows=[], macro_f1=0.0),
        ground_truth_dir=GROUND, tier="demo", fixture_root=DEMO,
    )
    for metric in changed.metrics:
        assert metric.numerator == 0, metric.metric_id
        assert metric.denominator > 0, metric.metric_id
    m4 = changed.metrics[3]
    assert m4.metric_id == "M4"
    assert m4.numerator == 0
    assert m4.denominator == 24  # 12 gold + 12 ungrounded tool mappings


def test_duplicate_emitted_feature_lowers_m2(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    correct = next(f for f in discovery.features if f.feature_id == "PA-VEH-01")
    bad = copy.deepcopy(discovery)
    bad.features = list(discovery.features) + [copy.deepcopy(correct)]
    changed = _evaluate(manifest, bad, reconstruction, review, comparison)
    assert changed.metrics[1].numerator == result.metrics[1].numerator
    assert changed.metrics[1].denominator == result.metrics[1].denominator + 1
    assert changed.metrics[1].value < result.metrics[1].value


def test_unlabelled_finding_lowers_m6(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    source = next(f for f in review.findings if f.rule_id == "PF-GW-NAM-001")
    evidence = make_evidence(
        evidence_id="REV-UNLABELLED",
        path="product/template/PersonalAutoTemplate.xml",
        locator=Locator(kind=LocatorKind.LINE, value="line 3", line=3),
        excerpt='<type name="PAVehicle">',
        method="lexer",
        confidence=Confidence.PARSED,
    )
    extra = copy.deepcopy(source)
    extra.finding_id = "F-UNLABELLED"
    extra.evidence_ids = [evidence.evidence_id]
    bad = copy.deepcopy(review)
    bad.findings.append(extra)
    bad.evidence.append(evidence)
    changed = _evaluate(manifest, discovery, reconstruction, bad, comparison)
    assert changed.metrics[5].denominator == result.metrics[5].denominator + 1
    assert changed.metrics[5].value < result.metrics[5].value


def test_m3_wrong_line_fails(demo_eval) -> None:
    _, discovery, _, _, _, _ = demo_eval
    evidence = next(item for item in discovery.evidence if item.locator.kind is LocatorKind.LINE)
    lines = (DEMO / evidence.path).read_text(encoding="utf-8").splitlines()
    bad = evidence.model_copy(deep=True)
    bad.locator.line = len(lines) if abs(len(lines) - evidence.locator.line) > 3 else 1
    assert audit_evidence_support(DEMO, bad) is False


def test_m3_wrong_xpath_fails(demo_eval) -> None:
    _, discovery, _, _, _, _ = demo_eval
    evidence = next(
        item for item in discovery.evidence
        if item.locator.kind is LocatorKind.XPATH and item.excerpt.startswith("<TypeKeyInput")
    )
    bad = evidence.model_copy(deep=True)
    bad.locator.value = "/PCF/Screen/TextInput[2]"
    assert audit_evidence_support(DEMO, bad) is False
    missing = evidence.model_copy(deep=True)
    missing.locator.value = "/PCF/Screen/DoesNotExist"
    assert audit_evidence_support(DEMO, missing) is False


def test_m3_fabricated_excerpt_fails(demo_eval) -> None:
    _, discovery, _, _, _, _ = demo_eval
    evidence = next(item for item in discovery.evidence if item.locator.kind is LocatorKind.XPATH)
    bad = make_evidence(
        evidence_id="EV-FABRICATED", path=evidence.path, locator=evidence.locator,
        excerpt="THIS EXCERPT DOES NOT EXIST", method=evidence.method,
        confidence=evidence.confidence,
    )
    assert audit_evidence_support(DEMO, bad) is False


def test_m3_mismatched_excerpt_sha_fails(demo_eval) -> None:
    _, discovery, _, _, _, _ = demo_eval
    evidence = next(item for item in discovery.evidence if item.locator.kind is LocatorKind.LINE)
    bad = evidence.model_copy(deep=True)
    bad.excerpt_sha = "0" * 64
    assert audit_evidence_support(DEMO, bad) is False
    bad_locator = evidence.model_copy(deep=True)
    bad_locator.locator.excerpt_sha = "0" * 64
    assert audit_evidence_support(DEMO, bad_locator) is False


def test_m5_wrong_file_finding_does_not_satisfy_issue(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    bad = copy.deepcopy(review)
    evidence_ids = {
        evidence_id
        for finding in bad.findings if finding.rule_id == "PF-GW-NAM-001"
        for evidence_id in finding.evidence_ids
    }
    assert evidence_ids
    for evidence in bad.evidence:
        if evidence.evidence_id in evidence_ids:
            evidence.path = "gsrc/acme/negatives/SafePatterns.gs"
    changed = _evaluate(manifest, discovery, reconstruction, bad, comparison)
    assert changed.metrics[4].numerator == result.metrics[4].numerator - 1


def test_m5_wrong_mapping_anchor_does_not_satisfy_issue(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    bad = copy.deepcopy(reconstruction)
    for mapping in bad.mappings:
        if mapping.rule_id == "R-CG-02":
            mapping.source_ref = "Unrelated.Source"
    changed = _evaluate(manifest, discovery, bad, review, comparison)
    assert changed.metrics[4].numerator == result.metrics[4].numerator - 1


def test_m5_top8_denominator_stays_stable_with_more_than_eight_issues(
    demo_eval, tmp_path: Path
) -> None:
    manifest, discovery, reconstruction, _, comparison, _ = demo_eval
    payload = json.loads(
        (GROUND / "estimate_moving_issues.json").read_text(encoding="utf-8")
    )
    issues = list(payload["issues"])
    issues.extend(
        {
            "id": f"EMI-X{index}", "statement": "Not emitted.",
            "signal_type": "finding_rule", "signal": "PF-GW-NOT-REAL", "impact": "low",
        }
        for index in range(4)
    )
    ground_truth = _ground_truth_with_issues(tmp_path, issues)
    changed = _evaluate(
        manifest, discovery, reconstruction, ReviewResult(), comparison, ground_truth
    )
    assert (changed.metrics[4].numerator, changed.metrics[4].denominator) == (3, 10)
    top8 = next(metric for metric in changed.supporting if metric.metric_id == "M5-TOP8")
    assert (top8.numerator, top8.denominator) == (3, 8)


def test_m5_top8_numerator_clamped_when_more_than_eight_detected(
    demo_eval, tmp_path: Path
) -> None:
    manifest, discovery, reconstruction, review, comparison, _ = demo_eval
    payload = json.loads(
        (GROUND / "estimate_moving_issues.json").read_text(encoding="utf-8")
    )
    issues = list(payload["issues"])
    issues.extend(
        {
            "id": f"EMI-D{index}", "statement": "Duplicate mapping signal.",
            "signal_type": "mapping_rule", "signal": "R-CG-02", "impact": "low",
        }
        for index in range(4)
    )
    ground_truth = _ground_truth_with_issues(tmp_path, issues)
    changed = _evaluate(
        manifest, discovery, reconstruction, review, comparison, ground_truth
    )
    assert (changed.metrics[4].numerator, changed.metrics[4].denominator) == (10, 10)
    top8 = next(metric for metric in changed.supporting if metric.metric_id == "M5-TOP8")
    assert (top8.numerator, top8.denominator) == (8, 8)
    assert changed.m5_precision == pytest.approx(1.0)


def test_schema_conformance_clamps_negative_numerator(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, _ = demo_eval
    bad = copy.deepcopy(reconstruction)
    bad.changes = bad.changes[:1]
    bad.validation_errors = ["one", "two", "three"]
    changed = _evaluate(manifest, discovery, bad, review, comparison)
    metric = next(
        item for item in changed.supporting if item.metric_id == "SCHEMA-CONFORMANCE"
    )
    assert (metric.numerator, metric.denominator) == (0, 1)
    assert metric.value == 0.0


def test_scaled_supporting_metrics_have_caveats_and_stay_in_range(demo_eval) -> None:
    *_, result = demo_eval
    supporting = {metric.metric_id: metric for metric in result.supporting}
    for metric_id in ("M6-MACRO", "REFERENCE-F1"):
        metric = supporting[metric_id]
        assert "scaled proportion, not a count" in metric.caveat.lower()
        assert 0 <= metric.numerator <= metric.denominator
        assert 0.0 <= metric.value <= 1.0


def test_m6_forged_evidence_on_gold_paths_scores_zero(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, _ = demo_eval
    assert len(review.findings) == 24
    forged = copy.deepcopy(review)
    for evidence in forged.evidence:
        evidence.excerpt = "FORGED EXCERPT NOT PRESENT IN THE SOURCE SNAPSHOT"
        evidence.excerpt_sha = hashlib.sha256(evidence.excerpt.encode("utf-8")).hexdigest()
        evidence.locator.kind = LocatorKind.LINE
        evidence.locator.line = 1
        evidence.locator.value = "line 1"
        evidence.locator.excerpt_sha = None
    changed = _evaluate(manifest, discovery, reconstruction, forged, comparison)
    m6 = changed.metrics[5]
    assert m6.numerator == 0
    assert all(stats["tp"] == 0 for stats in changed.per_rule.values())
    assert any(stats["fn"] == 3 for stats in changed.per_rule.values())


def test_m1_m2_broken_excerpts_lower_discovery(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    broken = copy.deepcopy(discovery)
    for evidence in broken.evidence:
        evidence.excerpt = "not-in-file"
        evidence.excerpt_sha = hashlib.sha256(evidence.excerpt.encode("utf-8")).hexdigest()
        if evidence.locator.excerpt_sha:
            evidence.locator.excerpt_sha = evidence.excerpt_sha
    changed = _evaluate(manifest, broken, reconstruction, review, comparison)
    assert changed.metrics[0].numerator < changed.metrics[0].denominator
    assert changed.metrics[1].numerator < changed.metrics[1].denominator
    assert changed.metrics[2].numerator == 0
    assert changed.metrics[0].numerator < result.metrics[0].numerator


def test_m3_all_links_audit_includes_appended_bad_item(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    bad = copy.deepcopy(discovery)
    bad_item = make_evidence(
        evidence_id="EV-BAD-TAIL",
        path="gsrc/acme/negatives/PublicApi.gs",
        locator=Locator(kind=LocatorKind.LINE, value="line 1", line=1),
        excerpt="FORGED TAIL EXCERPT NOT PRESENT IN THIS FILE",
        method="adversarial",
        confidence=Confidence.PARSED,
    )
    bad.evidence = list(discovery.evidence) + [bad_item]
    changed = _evaluate(manifest, bad, reconstruction, review, comparison)
    m3 = changed.metrics[2]
    assert m3.denominator == result.metrics[2].denominator + 1
    assert m3.numerator == result.metrics[2].numerator
    assert m3.value < 1.0


@pytest.mark.parametrize("excerpt", ["a", "TODO", "...", "not-in-file"])
def test_m3_trivial_or_placeholder_excerpt_fails(demo_eval, excerpt: str) -> None:
    _, discovery, _, _, _, _ = demo_eval
    source = discovery.evidence[0]
    bad = make_evidence(
        evidence_id="EV-TRIVIAL",
        path=source.path,
        locator=source.locator.model_copy(deep=True),
        excerpt=excerpt,
        method="adversarial",
        confidence=Confidence.PARSED,
    )
    assert audit_evidence_support(DEMO, bad) is False


def test_m3_path_escape_fails(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE SECRET CONTENT\n", encoding="utf-8")
    escaped = make_evidence(
        evidence_id="EV-ESCAPE",
        path="../outside.txt",
        locator=Locator(kind=LocatorKind.LINE, value="line 1", line=1),
        excerpt="OUTSIDE SECRET CONTENT",
        method="adversarial",
        confidence=Confidence.PARSED,
    )
    assert audit_evidence_support(root, escaped) is False
    etc = make_evidence(
        evidence_id="EV-ETC",
        path="../../etc/hostname",
        locator=Locator(kind=LocatorKind.LINE, value="line 1", line=1),
        excerpt="localhost",
        method="adversarial",
        confidence=Confidence.PARSED,
    )
    assert audit_evidence_support(root, etc) is False


def test_m3_all_demo_links_pass_and_sample_is_supporting(demo_eval) -> None:
    _, discovery, _, _, _, result = demo_eval
    m3 = result.metrics[2]
    assert m3.label == "Evidence-link support precision (all links)"
    assert len(discovery.evidence) == 101
    assert (m3.numerator, m3.denominator) == (101, 101)
    sample = next(metric for metric in result.supporting if metric.metric_id == "M3-SAMPLE")
    assert sample.label == "30-link stratified sample"
    assert (sample.numerator, sample.denominator) == (30, 30)
    assert sample.primary is False


@pytest.mark.parametrize(
    "payload",
    [
        {"numerator": 5, "denominator": 4},
        {"numerator": -2, "denominator": 4},
        {"numerator": 1, "denominator": 0},
    ],
)
def test_invalid_holdout_aggregate_is_clamped_with_caveat(
    demo_eval, tmp_path: Path, payload: dict
) -> None:
    manifest, discovery, reconstruction, review, comparison, _ = demo_eval
    target = tmp_path / "ground_truth"
    shutil.copytree(GROUND, target)
    path = target / "holdout_metrics.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(payload)
    data["caveat"] = "Synthetic invalid holdout payload."
    path.write_text(json.dumps(data), encoding="utf-8")
    changed = _evaluate(
        manifest, discovery, reconstruction, review, comparison, ground_truth_dir=target
    )
    metric = next(item for item in changed.supporting if item.metric_id == "HOLDOUT-RECALL")
    assert 0 <= metric.numerator <= metric.denominator
    assert "INVALID holdout aggregate; clamped for display." in metric.caveat
    assert changed.warnings


def test_absent_holdout_aggregate_is_explicitly_invalid(
    demo_eval, tmp_path: Path
) -> None:
    manifest, discovery, reconstruction, review, comparison, _ = demo_eval
    target = tmp_path / "ground_truth"
    shutil.copytree(GROUND, target)
    (target / "holdout_metrics.json").unlink()
    changed = _evaluate(
        manifest, discovery, reconstruction, review, comparison, ground_truth_dir=target
    )
    metric = next(item for item in changed.supporting if item.metric_id == "HOLDOUT-RECALL")
    assert metric.denominator > 0
    assert "INVALID holdout aggregate; clamped for display" in metric.caveat
    assert "aggregate absent" in metric.caveat
    assert changed.warnings


def test_mapping_grounding_rejects_empty_and_common_tokens(demo_eval) -> None:
    manifest, discovery, reconstruction, _, _, _ = demo_eval
    grounding = _mapping_grounding_text(DEMO, manifest, discovery)
    good = reconstruction.mappings[0]
    assert _mapping_grounded(good, grounding, manifest) is True

    empty = good.model_copy(deep=True)
    empty.source_ref = " "
    empty.source_name = " "
    assert _mapping_grounded(empty, grounding, manifest) is False

    common = good.model_copy(deep=True)
    common.source_ref = "Vehicle"
    common.source_name = "Vehicle"
    assert _mapping_grounded(common, grounding, manifest) is False

    empty_ref = good.model_copy(deep=True)
    empty_ref.source_ref = " "
    empty_ref.source_name = "Vehicle"
    assert _mapping_grounded(empty_ref, grounding, manifest) is False

    two_tokens = good.model_copy(deep=True)
    two_tokens.source_ref = "PAVehicle.Year"
    two_tokens.source_name = "Year"
    assert _mapping_grounded(two_tokens, grounding, manifest) is True


def test_grep_baseline_ignores_unlabelled_matching_files(demo_eval, tmp_path: Path) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    fixture = tmp_path / "fixture"
    shutil.copytree(DEMO, fixture)
    relative = "gsrc/acme/query/UnlabelledExtra.gs"
    extra = fixture / relative
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text(
        'package acme.query\nclass UnlabelledExtra {\n'
        '  function load() { DriverManager.getConnection("jdbc:acme:x") }\n}\n',
        encoding="utf-8",
    )
    changed_manifest = manifest.model_copy(deep=True)
    changed_manifest.artifacts.append(Artifact(
        path=relative,
        sha256=hashlib.sha256(extra.read_bytes()).hexdigest(),
        size=extra.stat().st_size,
        kind="gosu",
        parser="gosu",
        status=ArtifactStatus.PARSED,
        line_count=len(extra.read_text(encoding="utf-8").splitlines()),
    ))
    changed_manifest.file_count += 1
    changed_manifest.total_size += extra.stat().st_size

    changed = evaluate_run(
        fixture_id="demo-slice-300", manifest=changed_manifest,
        discovery=discovery, reconstruction=reconstruction, review=review,
        comparison=comparison, ground_truth_dir=GROUND, tier="demo",
        fixture_root=fixture,
    )
    assert changed.baselines["grep_only_findings"] == result.baselines["grep_only_findings"]
    assert changed.baselines["grep_only_findings_f1"] == result.baselines["grep_only_findings_f1"]


def test_m6_finding_with_a_forged_extra_link_is_not_fully_supported(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    changed_review = copy.deepcopy(review)
    target = next(
        finding for finding in changed_review.findings if finding.rule_id == "PF-GW-NAM-001"
    )
    valid = next(
        evidence for evidence in changed_review.evidence
        if evidence.evidence_id in target.evidence_ids
    )
    forged = make_evidence(
        evidence_id="REV-FORGED-SUPPORT",
        path=valid.path,
        locator=Locator(kind=LocatorKind.LINE, value="line 1", line=1),
        excerpt="FORGED SUPPORTING EXCERPT NOT PRESENT IN THE FILE",
        method="adversarial",
        confidence=Confidence.PARSED,
    )
    changed_review.evidence.append(forged)
    target.evidence_ids = [forged.evidence_id]
    changed = _evaluate(
        manifest, discovery, reconstruction, changed_review, comparison
    )
    assert changed.metrics[5].numerator < result.metrics[5].numerator


def test_m6_finding_from_an_extra_rule_is_a_false_positive(demo_eval) -> None:
    manifest, discovery, reconstruction, review, comparison, result = demo_eval
    source = next(f for f in review.findings if f.rule_id == "PF-GW-NAM-001")
    extra = copy.deepcopy(source)
    extra.finding_id = "F-BOGUS-RULE"
    extra.rule_id = "PF-GW-BOGUS-999"
    bad = copy.deepcopy(review)
    bad.findings.append(extra)
    changed = _evaluate(manifest, discovery, reconstruction, bad, comparison)
    assert changed.per_rule["UNLABELLED"]["fp"] >= 1
    assert changed.metrics[5].denominator > result.metrics[5].denominator
    assert changed.metrics[5].value < result.metrics[5].value


def test_invalid_xpath_locator_fails_instead_of_line_fallback(demo_eval) -> None:
    _, discovery, _, _, _, _ = demo_eval
    source = next(item for item in discovery.evidence if item.locator.kind is LocatorKind.LINE)
    forged = source.model_copy(deep=True)
    forged.locator = Locator(kind=LocatorKind.XPATH, value="not a valid xpath [[[", line=source.locator.line)
    assert audit_evidence_support(DEMO, forged) is False
