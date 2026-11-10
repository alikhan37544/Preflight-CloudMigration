"""Review tests: positives, hard negatives, claim strength, redaction.

Written before app/services/review.py exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.discovery import run_discovery
from app.services.intake import build_manifest
from app.services.review import run_review

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"


@pytest.fixture(scope="module")
def review():
    manifest = build_manifest(DEMO, snapshot_id="S-DEMO", project_id="P-DEMO")
    discovery = run_discovery(DEMO, manifest)
    return run_review(DEMO, manifest, discovery, include_thesis=False)


def findings_for(review, rule_id: str):
    return [f for f in review.findings if f.rule_id == rule_id]


def test_eight_demo_rules_produce_findings(review) -> None:
    rules = {f.rule_id for f in review.findings}
    assert rules == {
        "PF-GW-SQL-001", "PF-GW-SEC-001", "PF-GW-PKG-001", "PF-GW-EXC-001",
        "PF-GW-TX-001", "PF-GW-SRV-001", "PF-GW-NAM-001", "PF-GW-GUNIT-001",
    }


def test_each_positive_is_detected_once(review) -> None:
    expected = {
        "PF-GW-SQL-001": [
            "gsrc/acme/query/PersonalVehicleQuery.gs",
            "gsrc/acme/query/PersonalVehicleQueryB.gs",
            "gsrc/acme/query/PersonalVehicleQueryC.gs",
        ],
        "PF-GW-SEC-001": [
            "gsrc/acme/security/SecretConfig.gs",
            "gsrc/acme/security/SecretConfigB.gs",
            "gsrc/acme/security/SecretConfigC.gs",
        ],
        "PF-GW-PKG-001": [
            "gsrc/acme/internal/HiddenPackage.gs",
            "gsrc/acme/internal/HiddenPackageB.gs",
            "gsrc/acme/internal/HiddenPackageC.gs",
        ],
        "PF-GW-EXC-001": [
            "gsrc/acme/error/SwallowError.gs",
            "gsrc/acme/error/SwallowErrorB.gs",
            "gsrc/acme/error/SwallowErrorC.gs",
        ],
        "PF-GW-TX-001": [
            "gsrc/acme/transaction/BundleCommit.gs",
            "gsrc/acme/transaction/BundleCommitB.gs",
            "gsrc/acme/transaction/BundleCommitC.gs",
        ],
        "PF-GW-SRV-001": [
            "gsrc/acme/integration/LegacyVehicleServlet.gs",
            "gsrc/acme/integration/LegacyVehicleServletB.gs",
            "gsrc/acme/integration/LegacyVehicleServletC.gs",
        ],
        "PF-GW-GUNIT-001": [
            "gtest/acme/PersonalVehicleRatingDBTest.gs",
            "gtest/acme/PersonalVehicleRatingDBTestB.gs",
            "gtest/acme/PersonalVehicleRatingDBTestC.gs",
        ],
    }
    evidence_by_id = {e.evidence_id: e for e in review.evidence}
    for rule_id, paths in expected.items():
        matches = findings_for(review, rule_id)
        assert len(matches) == 3, (rule_id, [f.finding_id for f in matches])
        found_paths = {evidence_by_id[m.evidence_ids[0]].path for m in matches}
        assert found_paths == set(paths), rule_id


def test_hard_negatives_do_not_fire(review) -> None:
    by_rule = {}
    for finding in review.findings:
        for evidence_id in finding.evidence_ids:
            ev = next(e for e in review.evidence if e.evidence_id == evidence_id)
            by_rule.setdefault(finding.rule_id, set()).add(ev.path)

    assert "gsrc/acme/negatives/SafePatterns.gs" not in by_rule.get("PF-GW-SQL-001", set())
    assert "gsrc/acme/negatives/Placeholders.gs" not in by_rule.get("PF-GW-SEC-001", set())
    assert "gsrc/acme/negatives/SafePatterns.gs" not in by_rule.get("PF-GW-PKG-001", set())
    assert "gsrc/acme/negatives/CatchWithLogging.gs" not in by_rule.get("PF-GW-EXC-001", set())
    assert "gsrc/acme/negatives/NoCommit.gs" not in by_rule.get("PF-GW-TX-001", set())
    assert "gtest/acme/PersonalVehicleValidationTest.gs" not in by_rule.get("PF-GW-GUNIT-001", set())
    assert "gtest/acme/PersonalVehiclePureTest.gs" not in by_rule.get("PF-GW-GUNIT-001", set())


def test_names_rule_is_error_and_only_long_types(review) -> None:
    nam = findings_for(review, "PF-GW-NAM-001")
    assert len(nam) == 3
    assert all(f.severity.value == "error" for f in nam)
    messages = " ".join(f.message for f in nam)
    assert "PersonalAutoRatingFactorConfiguration" in messages
    assert "PersonalAutoUnderwritingConfiguration" in messages
    assert "PersonalAutoEligibilityConfiguration" in messages
    # Product-template type -> APD truncates on import -> endpoint compile
    # failure -> nameOverride maps the truncated visualized name to installed.
    assert "product-template type" in messages
    assert "truncates type names over 24" in messages
    assert "fails to compile" in messages
    assert "truncated visualized name" in messages
    assert "installed name" in messages
    assert "avoid truncation" not in messages
    for finding in nam:
        assert "avoid truncation" not in finding.remediation.lower()


def test_names_rule_metadata_uses_corrected_wording() -> None:
    from app.services.review import load_rules

    rule = next(r for r in load_rules() if r["rule_id"] == "PF-GW-NAM-001")
    assert "truncates product-template type names" in rule["title"].lower()
    assert "24" in rule["message"]
    assert "nameOverride" in rule["remediation"]
    assert "truncated visualized name" in rule["remediation"]
    assert "installed name" in rule["remediation"]


def test_claim_strength_and_standard_family(review) -> None:
    expectations = {
        "PF-GW-SQL-001": ("verified-id", "cloud-standard", "IS-TLS-1238"),
        "PF-GW-SEC-001": ("verified-id", "gosu-secure-coding", "SEC00-G"),
        "PF-GW-PKG-001": ("verified-id", "cloud-standard", "IS-TLS-1191"),
        "PF-GW-EXC-001": ("verified-id", "gosu-secure-coding", "ERR00-G"),
        "PF-GW-TX-001": ("secondary", "internal-guidance", None),
        "PF-GW-SRV-001": ("verified-policy", "hardening-guidance", None),
        "PF-GW-NAM-001": ("verified-doc", "none", None),
        "PF-GW-GUNIT-001": ("heuristic", "none", None),
    }
    for rule_id, (claim, family, standard_id) in expectations.items():
        finding = findings_for(review, rule_id)[0]
        assert finding.claim_strength.value == claim
        assert finding.standard_family.value == family
        assert finding.standard_id == standard_id


def test_secret_value_is_never_stored(review) -> None:
    raw_secret = "sk-live-9f3a7c2b6d1e"
    for finding in findings_for(review, "PF-GW-SEC-001"):
        assert raw_secret not in finding.message
        assert raw_secret not in (finding.remediation or "")
    for evidence in review.evidence:
        assert raw_secret not in evidence.excerpt
    redacted = [e for e in review.evidence if e.redacted]
    assert redacted
    assert any("REDACTED" in e.excerpt for e in redacted)


def test_no_generic_cloud_assurance_claim(review) -> None:
    for finding in review.findings:
        assert "cloud assurance" not in finding.message.lower()
        assert finding.rule_id.startswith("PF-")


def test_sbt_readiness_flag_is_separate(review) -> None:
    assert len(review.readiness) == 1
    flag = review.readiness[0]
    assert flag.rule_id == "PF-GW-SBT-001"
    assert flag.claim_strength.value == "heuristic"
    assert flag.standard_family.value == "none"
    assert flag.standard_id is None
    assert "heuristic" in flag.message.lower()
    assert "olos" in flag.message.lower()
    assert all(f.rule_id != "PF-GW-SBT-001" for f in review.findings)
