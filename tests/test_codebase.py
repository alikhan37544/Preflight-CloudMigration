"""Code-level migration tests: rules, refactors, SARIF, loop, resilience, API."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.case_studies import CASE_STUDIES, case_source_root, list_case_studies
from app.services.codeanalyzer import analyze_codebase, load_code_rules
from app.services.code_migration import run_code_migration, verify_code_audit
from app.services.refactor import apply_unified_diff, refactor_codebase
from app.services.resilience import (
    SCENARIOS,
    UNEXPECTED_SCENARIOS,
    evaluate_upgrade,
    guarded_scan,
    resilience_drills,
    resume_assessment,
    validate_patch_safety,
)
from app.services.sarif import build_sarif, sarif_json, sarif_summary

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures" / "case-studies"
CASCADE = FIXTURES / "cascade-mutual"
HARBOR = FIXTURES / "harbor-pc"


@pytest.fixture(scope="module")
def settings(tmp_path_factory) -> Settings:
    return Settings(
        data_dir=tmp_path_factory.mktemp("codebase-data"),
        fixtures_dir=REPO / "fixtures",
        secret_key="test-secret",
        sync_runs=True,
    )


@pytest.fixture(scope="module")
def api(settings):
    app = create_app(settings)
    with TestClient(app) as client:
        home = client.get("/codebase")
        token = re.search(r'name="csrf-token" content="([^"]+)"', home.text)
        assert token
        yield client, token.group(1)


@pytest.fixture(scope="module")
def cascade_result(settings):
    return run_code_migration("cascade-mutual", settings, max_iterations=3)


@pytest.fixture(scope="module")
def harbor_result(settings):
    return run_code_migration("harbor-pc", settings, max_iterations=3)


# -- rule pack and scanner -------------------------------------------------

def test_rule_pack_has_expected_cloud_blocker_families() -> None:
    pack = load_code_rules()
    rules = {rule["rule_id"]: rule for rule in pack["rules"]}
    expected = {
        "PF-CODE-SQL-001", "PF-CODE-SQL-002", "PF-CODE-SQL-003",
        "PF-CODE-MSG-001", "PF-CODE-SRV-001", "PF-CODE-API-001",
        "PF-CODE-API-002", "PF-CODE-SEC-001", "PF-CODE-SEC-002",
        "PF-CODE-MT-001", "PF-CODE-MT-002", "PF-CODE-TX-001",
        "PF-CODE-EXC-001", "PF-CODE-APD-001", "PF-CODE-GUNIT-001",
        "PF-CODE-LOG-001",
    }
    assert expected <= set(rules)
    assert all(rule["category"] for rule in rules.values())
    assert all(rule.get("cloud_target") for rule in rules.values())
    assert all(rule.get("autofix") for rule in rules.values())
    # Direct SQL keeps its documented hardening claim; heuristic rules never claim a standard ID.
    assert rules["PF-CODE-SQL-001"]["standard_id"] == "IS-TLS-1238"
    for rule in rules.values():
        if rule["claim_strength"] == "heuristic":
            assert rule.get("standard_id") is None
            assert rule.get("standard_family", "none") == "none"


def test_scanner_masks_comments_and_strings(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "gsrc").mkdir()
    (root / "gsrc" / "Safe.gs").write_text(
        "package acme.safe\n"
        "class Safe {\n"
        "  // DriverManager.getConnection in a comment is prose\n"
        "  var note = \"java.sql.Connection in a string is prose\"\n"
        "  function run() {\n"
        "    var q = Query.make(PersonalVehicle)\n"
        "    q.select()\n"
        "    var key = System.getenv(\"API_KEY\")\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    (root / "config").mkdir()
    (root / "config" / "safe.xml").write_text(
        '<?xml version="1.0"?>\n<config><!-- password="hunter2" -->'
        '<apiKey>${API_KEY}</apiKey></config>\n',
        encoding="utf-8",
    )
    (root / "config" / "safe.yaml").write_text(
        "# password: hunter2\napiKey: \"${API_KEY}\"\n",
        encoding="utf-8",
    )
    scan = analyze_codebase(root)
    assert scan.findings == []
    assert scan.score == 100


def test_scanner_flags_real_blockers_with_line_evidence() -> None:
    scan = analyze_codebase(CASCADE)
    rules = {finding.rule_id for finding in scan.findings}
    assert {
        "PF-CODE-SQL-001", "PF-CODE-SQL-002", "PF-CODE-MSG-001",
        "PF-CODE-SRV-001", "PF-CODE-SEC-001", "PF-CODE-MT-001",
        "PF-CODE-MT-002", "PF-CODE-TX-001", "PF-CODE-EXC-001",
        "PF-CODE-APD-001", "PF-CODE-GUNIT-001", "PF-CODE-LOG-001",
    } <= rules
    assert all(finding.line >= 1 for finding in scan.findings)
    assert all(finding.excerpt_sha and finding.fingerprint for finding in scan.findings)
    assert scan.by_severity["error"] > 0
    # The APD finding points at the long type, not line 1 by accident.
    apd = next(f for f in scan.findings if f.rule_id == "PF-CODE-APD-001")
    assert apd.line > 1
    assert "CascadePersonalAutoRatingFactorConfiguration" in apd.excerpt


def test_secret_findings_are_redacted_at_capture() -> None:
    scan = analyze_codebase(CASCADE)
    secrets = [f for f in scan.findings if f.rule_id == "PF-CODE-SEC-001"]
    assert secrets
    joined = "\n".join(f.excerpt for f in secrets)
    assert "cascade-live-7f2a91c4" not in joined
    assert "rotate-before-cloud" not in joined
    assert all(f.redacted for f in secrets)
    assert all("[REDACTED:" in f.excerpt for f in secrets)


def test_java_plugin_and_gunit_rules_fire() -> None:
    scan = analyze_codebase(HARBOR)
    rules = {finding.rule_id for finding in scan.findings}
    assert "PF-CODE-SEC-002" in rules
    assert "PF-CODE-GUNIT-001" in rules
    weak = next(f for f in scan.findings if f.rule_id == "PF-CODE-SEC-002")
    assert "MD5" in weak.excerpt


# -- Architect refactor ----------------------------------------------------

def test_refactor_produces_clean_target_and_applicable_diffs() -> None:
    scan = analyze_codebase(CASCADE)
    refactor = refactor_codebase(scan, source_root=CASCADE, address_severities={"error", "warning"})
    try:
        target = analyze_codebase(refactor.target_root)
        assert target.errors == 0
        assert target.warnings_count == 0
        assert refactor.patches
        assert all(patch["approval"] == "pending" for patch in refactor.patches)
        assert all(not patch["target_path"].startswith("_gen/") for patch in refactor.patches)

        for patch in refactor.patches:
            source_path = patch.get("source_path")
            if not source_path or patch.get("diff_redacted"):
                continue
            if source_path in refactor.deleted_files:
                continue
            target_text = refactor.target_texts.get(source_path)
            if target_text is None:
                continue
            applied = apply_unified_diff(scan.source_texts[source_path], patch["diff"])
            assert applied.rstrip("\n") == target_text.rstrip("\n"), patch["patch_id"]

        # The APD long type is covered by a codegen override and is clean on re-scan.
        assert "PF-CODE-APD-001" not in {finding.rule_id for finding in target.findings}
        assert refactor.overrides
        assert any(
            type_name.startswith("CascadePersonalAuto")
            for type_name in refactor.overrides
        )
        assert any(item["path"].startswith("config/codegen/") for item in refactor.added_files)

        # Secret literals never appear in target files or displayed diffs.
        target_join = "\n".join(refactor.target_texts.values())
        assert "cascade-live-7f2a91c4" not in target_join
        secret_diffs = "\n".join(
            patch["diff"] for patch in refactor.patches
            if "PF-CODE-SEC-001" in patch["rule_ids"]
        )
        assert "cascade-live-7f2a91c4" not in secret_diffs
        assert "[REDACTED:" in secret_diffs
    finally:
        refactor.cleanup()


def test_refactor_does_not_modify_source_and_generates_cloud_configs() -> None:
    before = hashlib.sha256(
        "\n".join(
            f"{path.relative_to(CASCADE)}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
            for path in sorted(CASCADE.rglob("*")) if path.is_file()
        ).encode("utf-8")
    ).hexdigest()
    scan = analyze_codebase(CASCADE)
    refactor = refactor_codebase(scan, source_root=CASCADE, address_severities={"error", "warning"})
    try:
        added = {item["path"] for item in refactor.added_files}
        assert any(path.startswith("config/cloudapi/") for path in added)
        assert any(path.startswith("config/appevents/") for path in added)
        assert any(path.startswith("config/secrets/") for path in added)
        assert any(path.startswith("config/codegen/") for path in added)
        assert any(path.endswith("CloudDataAccess.gs") for path in added)
        assert any(path.endswith("Resource.java") for path in added)
        for item in refactor.added_files:
            if item["path"].endswith((".yaml", ".yml")):
                yaml.safe_load((refactor.target_root / item["path"]).read_text(encoding="utf-8"))
            if item["path"].endswith(".xml"):
                from lxml import etree
                etree.fromstring((refactor.target_root / item["path"]).read_bytes())
    finally:
        refactor.cleanup()
    after = hashlib.sha256(
        "\n".join(
            f"{path.relative_to(CASCADE)}:{hashlib.sha256(path.read_bytes()).hexdigest()}"
            for path in sorted(CASCADE.rglob("*")) if path.is_file()
        ).encode("utf-8")
    ).hexdigest()
    assert before == after


# -- cyclic loop -----------------------------------------------------------

def test_cyclic_loop_reworks_then_turns_green(cascade_result) -> None:
    result = cascade_result
    assert result["status"] == "green_with_human_gates"
    assert result["green_signal"]["unified"] is True
    assert result["green_signal"]["guardian"] is True
    assert result["green_signal"]["critic"] is True
    assert result["green_signal"]["human_approval_required"] is True
    assert len(result["iterations"]) == 2
    first, second = result["iterations"]
    assert first["architect"]["mode"] == "error-first"
    assert first["guardian"]["verdict"] == "rework"
    assert first["critic"]["verdict"] == "rework"
    assert first["critic"]["fix_requests"]
    assert second["architect"]["mode"] == "full"
    assert second["guardian"]["verdict"] == "green"
    assert second["critic"]["verdict"] == "green"
    assert second["decision"] == "green"
    assert [agent["agent"] for agent in result["agents"]] == [
        "scout", "architect", "guardian", "critic", "planner",
    ]
    assert result["guardian"]["blocking"] == []
    assert result["critic"]["residual_risks"]
    assert all(risk["human_gate"] is True for risk in result["critic"]["residual_risks"])
    assert all(patch["approval"] == "pending" for patch in result["patches"])
    assert result["audit_verified"] is True
    assert verify_code_audit(result["audit"])[0] is True
    assert result["source_scan"]["snapshot_sha"] == result["resilience"]["after_hash"]
    assert result["target_scan"]["findings"] == []


def test_loop_budget_stops_without_false_green(settings) -> None:
    result = run_code_migration("cascade-mutual", settings, max_iterations=1)
    assert result["status"] == "blocked"
    assert result["green_signal"]["unified"] is False
    assert len(result["iterations"]) == 1
    assert result["iterations"][0]["guardian"]["verdict"] == "rework"
    assert result["iterations"][0]["critic"]["fix_requests"]
    assert result["planner"]["report_markdown"]


def test_upgrade_during_run_invalidates_green(settings) -> None:
    result = run_code_migration(
        "cascade-mutual", settings, max_iterations=2,
        upgrade_scenario="GWCP-APP-EVENTS-V2-2027.04",
    )
    assert result["status"] == "revalidation_required"
    assert result["green_signal"]["unified"] is False
    assert result["green_signal"]["guardian"] is False
    assert result["green_signal"]["critic"] is False
    assert result["upgrade"]["affected_patches"]
    assert result["audit_verified"] is True


def test_harbor_case_covers_more_families(harbor_result) -> None:
    result = harbor_result
    assert result["profile"]["name"] == "Harbor P&C"
    assert result["green_signal"]["unified"] is True
    categories = set(result["source_scan"]["by_category"])
    assert {"apd", "api", "crypto", "data_access", "messaging", "multitenancy",
            "security", "servlet", "testing", "transactions"} <= categories
    assert len(result["profile"]["lobs"]) == 3
    assert result["critic"]["residual_risks"]
    assert result["patches"]


def test_agent_failure_is_contained(monkeypatch, settings) -> None:
    from app.services import code_migration

    monkeypatch.setattr(
        code_migration, "refactor_codebase",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("architect boom")),
    )
    result = run_code_migration("cascade-mutual", settings, max_iterations=2)
    assert result["status"] == "failed"
    assert "architect boom" in result["error"]["message"]
    assert result["source_scan"]["files_scanned"] > 0
    assert result["green_signal"]["unified"] is False


def test_upgrade_rerun_uses_effective_apd_limit(settings) -> None:
    result = run_code_migration(
        "cascade-mutual", settings, max_iterations=2,
        upgrade_scenario="GWCP-APD-NAMING-2027.04",
    )
    assert result["status"] == "green_with_human_gates"
    assert result["upgrade"]["status"] == "compatible"
    assert all(len(value) <= 20 for value in result["overrides"].values())


def test_audit_tampering_is_detected(cascade_result) -> None:
    audit = json.loads(json.dumps(cascade_result["audit"]))
    audit[-1]["reason"] = "tampered"
    ok, detail = verify_code_audit(audit)
    assert ok is False
    assert "hash mismatch" in detail


def test_case_study_profiles_are_explicitly_synthetic() -> None:
    profiles = list_case_studies()
    assert {profile["case_id"] for profile in profiles} == {"cascade-mutual", "harbor-pc"}
    for profile in profiles:
        assert profile["lobs"]
        assert profile["custom_features"]
        assert profile["constraints"]
        assert profile["case_thesis"]
        assert profile["footprint"]["policies"]
    assert case_source_root(Settings(fixtures_dir=REPO / "fixtures"), "cascade-mutual").is_dir()


# -- SARIF -----------------------------------------------------------------

def test_sarif_is_2_1_0_and_does_not_leak_secrets(cascade_result) -> None:
    sarif = cascade_result["sarif"]["json"]
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"].endswith("sarif-2.1.0.json")
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "PreFlight CodeGuard"
    assert len(run["tool"]["driver"]["rules"]) >= 10
    assert len(run["results"]) == len(cascade_result["findings"])
    for result in run["results"]:
        assert result["ruleId"]
        assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        assert result["locations"][0]["physicalLocation"]["region"]["startLine"] >= 1
        assert result["partialFingerprints"]["primaryLocationLineHash"]
    text = sarif_json(sarif)
    assert "cascade-live-7f2a91c4" not in text
    assert "rotate-before-cloud" not in text
    summary = sarif_summary(sarif)
    assert summary["version"] == "2.1.0"
    assert summary["results"] == len(cascade_result["findings"])


def test_sarif_can_be_built_directly_from_a_scan() -> None:
    scan = analyze_codebase(HARBOR)
    sarif = build_sarif(scan.findings, run_label="harbor-pc")
    assert sarif["runs"][0]["properties"]["official_cloud_assurance"] is False
    assert sarif["runs"][0]["properties"]["result_count"] == len(scan.findings)
    assert "harbor-live-2b9d8e71" not in sarif_json(sarif)


# -- resilience ------------------------------------------------------------

def test_upgrade_invalidates_green_and_offers_resume(cascade_result) -> None:
    impact = evaluate_upgrade(cascade_result, "GWCP-APD-NAMING-2027.04")
    assert impact["status"] == "revalidation_required"
    assert impact["green_signal_before"]["unified"] is True
    assert impact["green_signal_after"]["unified"] is False
    assert impact["affected_patches"]
    assert impact["event"]["new_generation"] == cascade_result["generation"] + 1
    assert any(option["recommended"] for option in impact["resume_options"])
    updated = resume_assessment(cascade_result, impact, "revalidate")
    assert updated["status"] == "resume_requested"
    assert updated["resume"]["requires_human_approval"] is True
    assert updated["green_signal"]["unified"] is False
    assert verify_code_audit(updated["audit"])[0] is True


def test_every_upgrade_scenario_is_revalidated(cascade_result) -> None:
    for scenario_id in SCENARIOS:
        impact = evaluate_upgrade(cascade_result, scenario_id)
        assert impact["scenario"]["scenario_id"] == scenario_id
        assert impact["status"] == "revalidation_required"
        assert impact["event"]["invalidates_green"] is True


def test_unexpected_scenario_playbook_is_named() -> None:
    drills = resilience_drills()
    assert {item["kind"] for item in drills} == set(UNEXPECTED_SCENARIOS)
    assert all(item["handling"] and item["recovery"] for item in drills)


def test_guarded_scan_detects_source_change(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "a.gs").write_text("package a\nclass A {}\n", encoding="utf-8")
    from app.services import resilience

    values = iter(["before", "after"])
    monkeypatch.setattr(resilience, "_tree_hash", lambda _root: next(values))
    guarded = resilience.guarded_scan(root)
    assert guarded.status == "source_changed"
    assert guarded.error["kind"] == "source-changed"


def test_guarded_scan_contains_analyzer_crash(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    root.mkdir()
    (root / "a.gs").write_text("package a\nclass A {}\n", encoding="utf-8")
    from app.services import resilience

    monkeypatch.setattr(resilience, "analyze_codebase", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    guarded = resilience.guarded_scan(root)
    assert guarded.status == "analyzer_failed"
    assert guarded.error["kind"] == "analyzer-crash"


def test_guarded_scan_empty_snapshot_is_named(tmp_path: Path) -> None:
    root = tmp_path / "empty-snapshot"
    root.mkdir()
    guarded = guarded_scan(root)
    assert guarded.status == "insufficient_evidence"
    assert guarded.error["kind"] == "empty-snapshot"
    assert guarded.scan is not None
    assert guarded.scan.files_scanned == 0


def test_patch_safety_blocks_duplicates_unsafe_and_gen_targets() -> None:
    issues = validate_patch_safety([
        {"patch_id": "CP-01", "target_path": "gsrc/a.gs"},
        {"patch_id": "CP-02", "target_path": "gsrc/a.gs"},
        {"patch_id": "CP-03", "target_path": "../escape.gs"},
        {"patch_id": "CP-04", "target_path": "_gen/a.gs"},
    ])
    kinds = {item["kind"] for item in issues}
    assert {"duplicate-target", "unsafe-path", "gen-edit"} <= kinds


# -- API and pages ---------------------------------------------------------

def test_codebase_pages_and_api(api) -> None:
    client, token = api
    page = client.get("/codebase?case=cascade-mutual")
    assert page.status_code == 200
    text = page.text
    assert "Cascade Mutual" in text
    assert "cyclic" in text
    assert "Guardian deterministic gate" in text
    assert "SARIF 2.1.0" in text
    assert "Mid-migration upgrade resilience" in text
    assert "Human review gates" in text

    profiles = client.get("/case-studies")
    assert profiles.status_code == 200
    assert "Cascade Mutual" in profiles.text
    assert "Harbor P&amp;C" in profiles.text

    upgraded = client.get("/codebase?case=cascade-mutual&upgrade=GWCP-APD-NAMING-2027.04")
    assert upgraded.status_code == 200
    assert "revalidation_required" in upgraded.text
    assert "affected patch" in upgraded.text.lower()

    cases = client.get("/api/codebase/cases").json()
    assert len(cases["cases"]) == 2
    assert cases["upgrade_scenarios"]

    payload = client.get("/api/codebase/cases/cascade-mutual").json()
    assert payload["status"] == "green_with_human_gates"
    assert payload["green_signal"]["unified"] is True
    assert "cascade-live-7f2a91c4" not in client.get("/api/codebase/cases/cascade-mutual").text

    sarif = client.get("/api/codebase/cases/cascade-mutual/sarif")
    assert sarif.status_code == 200
    assert sarif.headers["content-type"].startswith("application/sarif+json")
    assert json.loads(sarif.text)["version"] == "2.1.0"

    report = client.get("/api/codebase/cases/cascade-mutual/report")
    assert report.status_code == 200
    assert "Codebase migration report" in report.text

    audit = client.get("/api/codebase/cases/cascade-mutual/audit").json()
    assert audit["verified"] is True

    patch_id = payload["patches"][0]["patch_id"]
    patch = client.get(f"/api/codebase/cases/cascade-mutual/patches/{patch_id}")
    assert patch.status_code == 200
    assert patch.text.startswith("---") or patch.text.startswith("+++") or "b/" in patch.text

    bundle = client.get("/api/codebase/cases/cascade-mutual/bundle.zip")
    assert bundle.status_code == 200
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        names = archive.namelist()
        assert "bundle-manifest.json" in names
        assert "sarif/results.sarif" in names
        assert "MIGRATION-REPORT.md" in names
        assert any(name.startswith("target/") for name in names)
        assert any(name.startswith("patches/") for name in names)


def test_codebase_post_endpoints_require_csrf(api) -> None:
    client, token = api
    missing = client.post("/api/codebase/cases/cascade-mutual/run", json={"max_iterations": 2})
    assert missing.status_code == 403
    allowed = client.post(
        "/api/codebase/cases/cascade-mutual/run",
        json={"max_iterations": 2},
        headers={"X-CSRF-Token": token},
    )
    assert allowed.status_code == 200
    assert allowed.json()["green_signal"]["unified"] is True


def test_upgrade_and_resume_api(api) -> None:
    client, token = api
    impact = client.post(
        "/api/codebase/cases/cascade-mutual/upgrade",
        json={"scenario_id": "GWCP-APD-NAMING-2027.04"},
        headers={"X-CSRF-Token": token},
    )
    assert impact.status_code == 200
    assert impact.json()["status"] == "revalidation_required"
    resumed = client.post(
        "/api/codebase/cases/cascade-mutual/resume",
        json={"scenario_id": "GWCP-APD-NAMING-2027.04", "choice": "rollback"},
        headers={"X-CSRF-Token": token},
    )
    assert resumed.status_code == 200
    assert resumed.json()["result"]["status"] == "rolled_back_to_checkpoint"
    unknown = client.post(
        "/api/codebase/cases/cascade-mutual/upgrade",
        json={"scenario_id": "not-a-scenario"},
        headers={"X-CSRF-Token": token},
    )
    assert unknown.status_code == 400


def test_unknown_case_is_404(api) -> None:
    client, _ = api
    assert client.get("/api/codebase/cases/unknown").status_code == 404
    assert client.get("/codebase?case=unknown").status_code == 404
