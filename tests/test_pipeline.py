"""End-to-end pipeline test (no HTTP): artifacts, audit, metrics, packet.

Written before app/services/pipeline.py exists.
"""

from __future__ import annotations

import json
import shutil
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
    for name in ("evidence.json", "review_evidence.json", "findings.json",
                 "packet.html", "packet.json"):
        text = (store.run_dir("R-PIPE") / name).read_text(encoding="utf-8")
        for secret in SECRET_LITERALS:
            assert secret not in text, (name, secret)
    packet_html = (store.run_dir("R-PIPE") / "packet.html").read_text(encoding="utf-8")
    assert "REDACTED" in packet_html
    findings = store.read_artifact("R-PIPE", "findings.json")
    assert any("Value redacted (fingerprint " in finding["message"]
               for finding in findings["findings"]
               if finding["rule_id"] == "PF-GW-SEC-001")
