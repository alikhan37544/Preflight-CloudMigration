"""End-to-end pipeline test (no HTTP): artifacts, audit, metrics, packet.

Written before app/services/pipeline.py exists.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from html import unescape
from pathlib import Path

import pytest

from app.services.intake import snapshot_hash
from app.services.packet import (
    PacketIntegrityError,
    build_packet,
    packet_content_hash,
    packet_html_hash,
    verify_packet_artifacts,
)
from app.services.pipeline import execute_run
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"
REFERENCE = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    store = RunStore(tmp_path_factory.mktemp("data"))
    store.create_run("R-PIPE", project_id="demo", snapshot_id="S-DEMO")
    result = execute_run(
        DEMO, store, "R-PIPE", project_id="demo", fixture_id="demo-slice-300",
        tier="demo", reference_path=REFERENCE,
    )
    return store, result


def test_run_succeeds_and_persists_artifacts(run) -> None:
    store, result = run
    status = store.read_status("R-PIPE")
    assert status["status"] == "succeeded"
    expected = [
        "manifest.json", "features.json", "evidence.json", "gaps.json", "spine.json",
        "findings.json", "mappings.json", "changes.json", "assumptions.json",
        "comparison.json", "metrics.json", "packet.json", "packet.html", "audit.jsonl",
        "status.json",
    ]
    for name in expected:
        assert store.exists("R-PIPE", name), name


def test_metrics_are_persisted_with_caveats(run) -> None:
    store, _ = run
    payload = store.read_artifact("R-PIPE", "metrics.json")
    metrics = payload["metrics"]
    assert [m["metric_id"] for m in metrics] == ["M1", "M2", "M3", "M4", "M5", "M6"]
    for metric in metrics:
        assert metric["denominator"] > 0
        assert metric["caveat"]


def test_packet_has_six_pages_and_disclaimers(run) -> None:
    store, result = run
    packet = store.read_artifact("R-PIPE", "packet.json")
    assert len(packet["pages"]) == 6
    assert "Cloud Assurance: not run" in packet["disclaimer"]
    html = (store.run_dir("R-PIPE") / "packet.html").read_text(encoding="utf-8")
    assert "Official Cloud Assurance: not run" in html
    assert "not affiliated" in html.lower()
    assert "Synthetic" in html
    assert "sk-live-9f3a7c2b6d1e" not in html
    expected_boundary = (
        "Cloud Retrofit without APD App; not Guidewire&#39;s recommended process; "
        "local, non-deployable draft; field-level nameOverride only applies on this path."
    )
    assert expected_boundary in html
    assert "Scope boundary" in html
    assert "Cloud Retrofit boundary." in html
    assert "<main class=\"page\">" in html
    assert html.count("<thead>") >= 10
    assert html.count("<caption>") >= 10
    assert 'scope="col"' in html
    assert 'scope="row"' in html


def test_packet_table_captions_follow_each_tables_headers(run) -> None:
    """Captions must come from the table they label, not a positional list.

    A positional list shifts every caption when a finding rule is added or
    removed; the old code even labelled a finding table "Readiness flags".
    """
    store, _ = run
    html = (store.run_dir("R-PIPE") / "packet.html").read_text(encoding="utf-8")
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, flags=re.S)
    assert len(tables) >= 10
    finding_tables = 0
    for index, inner in enumerate(tables):
        caption_match = re.search(r"<caption>(.*?)</caption>", inner, flags=re.S)
        assert caption_match, f"table {index} has no caption"
        caption = unescape(caption_match.group(1)).strip()
        assert caption, f"table {index} has an empty caption"
        first_row = re.search(r"<tr[^>]*>(.*?)</tr>", inner, flags=re.S)
        assert first_row, f"table {index} has no header row"
        header_cells = re.findall(r"<th[^>]*>(.*?)</th>", first_row.group(1), flags=re.S)
        if index == 0:
            assert caption == "Packet cover"
            continue
        assert header_cells, f"table {index} has no header cells"
        if not re.search(r"<td[^>]*>", first_row.group(1)):
            labels = [
                re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", cell))).strip()
                for cell in header_cells
            ]
            for label in dict.fromkeys(labels):
                assert label in caption, (caption, label)
        if "Decision" in first_row.group(1):
            finding_tables += 1
            assert caption.startswith("Table: Finding")
            assert "Readiness flags" not in caption
    assert finding_tables >= 2
    assert "Readiness flags" not in "\n".join(
        unescape(re.search(r"<caption>(.*?)</caption>", table, flags=re.S).group(1))
        for table in tables
    )
    readiness_tables = [table for table in tables if "Flag</th>" in table]
    assert readiness_tables
    for table in readiness_tables:
        caption = unescape(re.search(r"<caption>(.*?)</caption>", table, flags=re.S).group(1))
        assert caption.startswith("Table: Flag")
    # Mobile keeps the header row visible and scrolls the wrapper instead of
    # stacking cells without labels.
    assert "thead { display: none" not in html
    assert 'role="group" aria-label="Table: Finding' in html
    assert 'data-columns="7"' in html
    assert "table[data-columns=\"7\"] { min-width: 760px; }" in html


def test_codegen_draft_keeps_garage_location_names_coherent(run) -> None:
    import yaml

    store, _ = run
    draft = store.run_dir("R-PIPE") / "draft"
    codegen = yaml.safe_load((
        draft / "config/integration/apis/installedlobs/pa_codegen_config_ext-1.0.yaml"
    ).read_text(encoding="utf-8"))
    garage = codegen["types"]["PAVehicle"]["fields"]["GarageLocation"]
    assert garage == {"nameOverride": "GarageLocation_Ext", "requiredForCreate": False}


def test_audit_chain_verifies(run) -> None:
    store, _ = run
    assert store.verify_audit("R-PIPE") is True
    events = store.read_audit("R-PIPE")
    assert any(e["action"].startswith("stage.") for e in events)
    assert events[-1]["action"] == "run.succeeded"


def test_source_is_untouched(run) -> None:
    _, result = run
    assert snapshot_hash(DEMO) == result.manifest.sha256


def test_pipeline_exposes_reconstruction_and_comparison(run) -> None:
    _, result = run
    assert len(result.reconstruction.mappings) == 12
    assert len(result.reconstruction.assumptions) == 3
    assert result.comparison is not None
    assert result.comparison.macro_f1 == pytest.approx(1.0)
    assert result.evaluation is not None


def test_immutability_artifact_is_written(run) -> None:
    store, result = run
    payload = store.read_artifact("R-PIPE", "immutability.json")
    assert payload["unchanged"] is True
    assert payload["before"] == payload["after"] == result.manifest.sha256


def test_every_feature_keeps_a_spine(run) -> None:
    store, result = run
    payload = store.read_artifact("R-PIPE", "spine.json")
    feature_ids = {feature.feature_id for feature in result.discovery.features}
    assert len(feature_ids) == 8
    assert set(payload["spines"]) == feature_ids
    for feature_id in feature_ids:
        assert payload["spines"][feature_id]["nodes"], feature_id
    # The reconstructed feature keeps its inventory nodes and gains target nodes.
    pa_veh = payload["spines"]["PA-VEH-01"]
    node_ids = {node["id"] for node in pa_veh["nodes"]}
    assert any(node_id.startswith("pcf:") for node_id in node_ids)
    assert any(node_id.startswith("schema:") for node_id in node_ids)
    assert any(node_id.startswith("codegen:") for node_id in node_ids)


def test_packet_audit_head_and_counts_are_current(run) -> None:
    store, _ = run
    packet = store.read_artifact("R-PIPE", "packet.json")
    audit = store.read_audit("R-PIPE")
    assert packet["audit_head"] == audit[-1]["hash"]
    assert packet["audit_verified"] is True
    assert packet["audit_event_count"] == len(audit)
    assert packet["counts"]["audit_events"] == len(audit)
    assert packet["counts"]["findings"] == len(
        store.read_artifact("R-PIPE", "findings.json")["findings"]
    )


def test_packet_hash_is_reproducible(run) -> None:
    store, _ = run
    packet = store.read_artifact("R-PIPE", "packet.json")
    html = (store.run_dir("R-PIPE") / "packet.html").read_text(encoding="utf-8")
    assert packet["hashes"]["packet"] == packet["packet_sha256"]
    assert packet["hashes"]["packet_html"] == packet["packet_sha256"]
    assert packet["hashes"]["packet_json"] == packet_content_hash(packet)
    assert packet_html_hash(html, packet["packet_sha256"]) == packet["packet_sha256"]
    assert f'<meta name="packet-sha256" content="{packet["packet_sha256"]}">' in html
    valid, reason = verify_packet_artifacts(store, "R-PIPE", include_content=True)
    assert valid, reason


def test_tampered_packet_html_is_detected(run, tmp_path) -> None:
    store, _ = run
    copied = tmp_path / "tamper-html-data"
    shutil.copytree(store.base_dir, copied)
    copy_store = RunStore(copied)
    path = copy_store.run_dir("R-PIPE") / "packet.html"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "Review Packet", "Review Packet (edited)"
    ), encoding="utf-8")
    valid, reason = verify_packet_artifacts(copy_store, "R-PIPE", include_content=True)
    assert valid is False
    assert "packet.html" in reason and "SHA-256" in reason


def test_cli_verify_packet_reports_ok(run, capsys) -> None:
    from app.cli import main as cli_main

    store, _ = run
    status = cli_main(["--data", str(store.base_dir), "verify-packet", "R-PIPE"])
    captured = capsys.readouterr()
    assert status == 0
    assert "R-PIPE: OK" in captured.out
    assert "content digests" in captured.out


def test_cli_verify_packet_detects_tampered_html(run, tmp_path, capsys) -> None:
    from app.cli import main as cli_main

    store, _ = run
    copied = tmp_path / "tamper-cli-data"
    shutil.copytree(store.base_dir, copied)
    copy_store = RunStore(copied)
    path = copy_store.run_dir("R-PIPE") / "packet.html"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "Review Packet", "Review Packet (edited)"
    ), encoding="utf-8")
    status = cli_main(["--data", str(copied), "verify-packet", "R-PIPE"])
    captured = capsys.readouterr()
    assert status == 1
    assert "R-PIPE: TAMPERED" in captured.out
    assert "packet.html" in captured.out
    assert "SHA-256" in captured.out


def test_tampered_packet_json_is_detected(run, tmp_path) -> None:
    store, _ = run
    copied = tmp_path / "tamper-json-data"
    shutil.copytree(store.base_dir, copied)
    copy_store = RunStore(copied)
    packet = copy_store.read_artifact("R-PIPE", "packet.json")
    # Editing the packet's findings/mapping digest (or any metadata) must break
    # the canonical JSON hash even though packet.html is untouched.
    packet["hashes"]["findings"] = "0" * 64
    packet["counts"]["mappings"] = 11
    copy_store.write_artifact("R-PIPE", "packet.json", packet)
    valid, reason = verify_packet_artifacts(copy_store, "R-PIPE", include_content=True)
    assert valid is False
    assert "packet.json" in reason and "packet_json" in reason


def test_edited_findings_artifact_breaks_packet_content_binding(run, tmp_path) -> None:
    store, _ = run
    copied = tmp_path / "tamper-findings-data"
    shutil.copytree(store.base_dir, copied)
    copy_store = RunStore(copied)
    findings = copy_store.read_artifact("R-PIPE", "findings.json")
    findings["findings"][0]["message"] += " edited after packet generation"
    copy_store.write_artifact("R-PIPE", "findings.json", findings)
    valid, reason = verify_packet_artifacts(copy_store, "R-PIPE", include_content=True)
    assert valid is False
    assert "findings" in reason and "content digest" in reason


def test_documented_packet_fallback_has_accessible_tables() -> None:
    html = (REPO / "docs/demo/preflight-review-packet.html").read_text(encoding="utf-8")
    assert '<main class="page">' in html
    assert html.count("<caption>") >= 10
    assert "<thead>" in html
    assert 'scope="col"' in html
    assert 'scope="row"' in html
    assert "thead { display: none" not in html
    assert 'role="group" aria-label="Table: Finding' in html


def test_packet_carries_readiness_evidence_mappings_and_excluded_files(run) -> None:
    store, _ = run
    packet = store.read_artifact("R-PIPE", "packet.json")
    counts = packet["counts"]
    assert counts["readiness"] >= 1
    assert counts["mappings"] == 12
    assert counts["changes"] == 5
    assert counts["unsupported_files"] == 4
    assert counts["discovery_evidence"] == 101
    assert counts["evidence"] == counts["discovery_evidence"] + counts["review_evidence"]
    html = (store.run_dir("R-PIPE") / "packet.html").read_text(encoding="utf-8")
    assert "Readiness flags" in html
    assert "Mapping and disposition ledger" in html
    assert "Excluded and unsupported files (4)" in html
    assert "Audit chain verified: yes" in html
    assert f"Complete evidence set: {counts['evidence']} items" in html
    assert "Discovery evidence (101)" in html
    assert "data/vehicle_rating_inputs.csv" in html
    assert "packet_sha256" in packet


def test_tampered_audit_fails_packet_build(run, tmp_path) -> None:
    store, result = run
    copied = tmp_path / "data"
    shutil.copytree(store.base_dir, copied)
    copy_store = RunStore(copied)
    audit_path = copy_store.run_dir("R-PIPE") / "audit.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["action"] = "stage.tampered"
    lines[0] = json.dumps(first, ensure_ascii=False)
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert copy_store.verify_audit("R-PIPE") is False
    valid, reason = verify_packet_artifacts(copy_store, "R-PIPE", include_content=True)
    assert valid is False
    assert "audit" in reason.lower()
    with pytest.raises(PacketIntegrityError):
        build_packet(
            store=copy_store, run_id="R-PIPE", project_id="demo",
            fixture_id="demo-slice-300", release_context="Qusar 2026.08 (review context)",
            manifest=result.manifest, discovery=result.discovery, review=result.review,
            reconstruction=result.reconstruction, comparison=result.comparison,
            evaluation=result.evaluation, reference_path=REFERENCE,
        )


SECRET_LITERALS = (
    "sk-live-9f3a7c2b6d1e",
    "tok-live-4b8c1d",
    "s3cr3t-live-value",
    "CHANGEME",
)


def test_persisted_artifacts_never_contain_fixture_secrets(run) -> None:
    store, _ = run
    run_dir = store.run_dir("R-PIPE")
    names = (
        "evidence.json", "review_evidence.json", "findings.json",
        "mappings.json", "changes.json", "assumptions.json",
        "decisions.json", "audit.jsonl", "packet.html", "packet.json",
    )
    for name in names:
        path = run_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for secret in SECRET_LITERALS:
            assert secret not in text, (name, secret)
    packet_html = (run_dir / "packet.html").read_text(encoding="utf-8")
    assert "REDACTED" in packet_html
    findings = store.read_artifact("R-PIPE", "findings.json")
    assert any("Value redacted (fingerprint " in finding["message"]
               for finding in findings["findings"]
               if finding["rule_id"] == "PF-GW-SEC-001")


def test_autonomous_migrator_generates_a_verified_bundle(run) -> None:
    from app.services.migrator import (
        PLAN_PATH, REPORT_PATH, run_migration, verify_migration_log,
    )

    store, _ = run
    state = run_migration(store, "R-PIPE", pace=0.0)
    assert state["status"] == "completed_with_gates"
    assert state["verification"]["status"] == "passed"
    assert state["summary"]["packages"] == len(state["packages"]) == 5
    assert state["summary"]["generated"] == 5
    assert state["summary"]["gates"] >= 1
    assert all(package["approval"] == "pending" for package in state["packages"])
    assert all("_gen" not in package["target_path"] for package in state["packages"])
    assert store.exists("R-PIPE", PLAN_PATH)
    assert store.exists("R-PIPE", REPORT_PATH)
    assert store.exists("R-PIPE", "migration/bundle-manifest.json")
    report = store.read_artifact("R-PIPE", REPORT_PATH)
    assert "completed_with_gates" in report
    assert "Plan SHA-256: `" in report
    bundle = store.read_artifact("R-PIPE", "migration/bundle-manifest.json")
    report_entry = next(item for item in bundle["files"] if item["path"].endswith("MIGRATION-REPORT.md"))
    assert report_entry["sha256"] == hashlib.sha256(report.encode("utf-8")).hexdigest()
    for package in state["packages"]:
        assert store.exists("R-PIPE", f"migration/target/{package['target_path']}")
        assert package["status"] == "draft_ready"
        assert package["evidence_ids"]
    ok, detail = verify_migration_log(store, "R-PIPE")
    assert ok, detail
    assert state["audit"]["verified"] is True


def test_migrator_agent_log_detects_tampering(run) -> None:
    from app.services.migrator import AUDIT_PATH, run_migration, verify_migration_log

    store, _ = run
    run_migration(store, "R-PIPE", pace=0.0)
    assert verify_migration_log(store, "R-PIPE")[0] is True
    path = store.run_dir("R-PIPE") / AUDIT_PATH
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[-1] = lines[-1].replace('"reason": "completed_with_gates"', '"reason": "tampered"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, detail = verify_migration_log(store, "R-PIPE")
    assert ok is False
    assert "hash mismatch" in detail
