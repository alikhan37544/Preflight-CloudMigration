"""API and product-shell tests: routes, CSRF, decisions, assistant, immutability.

Written before app/main.py exists.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.intake import snapshot_hash
from app.store import RunStore, StoreError

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("api-data")
    settings = Settings(
        data_dir=data_dir,
        fixtures_dir=REPO / "fixtures",
        reference_path=REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json",
        secret_key="test-secret",
        sync_runs=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        home = client.get("/")
        token = re.search(r'name="csrf-token" content="([^"]+)"', home.text)
        assert token, "home page must expose a CSRF token"
        yield client, token.group(1)


@pytest.fixture(scope="module")
def run_id(api):
    client, token = api
    response = client.post(
        "/api/runs",
        json={"project_id": "demo", "fixture_id": "demo-slice-300", "force": True},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] in {"queued", "running", "succeeded"}
    return payload["run_id"]


def test_health(api) -> None:
    client, _ = api
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/health").json()["status"] == "ok"
    models = client.get("/v1/models")
    assert models.status_code == 200
    assert models.json()["data"] == []


def test_product_pages_render(api, run_id) -> None:
    client, _ = api
    for path in ["/", "/manifest", "/reconstruction", "/findings", "/evaluation", "/packet", "/runs", "/about", "/settings"]:
        response = client.get(f"{path}?run={run_id}")
        assert response.status_code == 200, path
        assert "PreFlight" in response.text


def test_workbench_shows_feature_and_disclaimer(api, run_id) -> None:
    client, _ = api
    response = client.get(f"/?run={run_id}&feature=PA-VEH-01")
    text = response.text
    assert "PA-VEH-01" in text
    assert "Synthetic" in text
    assert "Cloud Assurance: not run" in text
    assert "Vehicle Information" in text


def test_manifest_api_paginates(api, run_id) -> None:
    client, _ = api
    response = client.get(f"/api/runs/{run_id}/manifest?page=1&size=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 300
    assert len(payload["artifacts"]) == 10


def test_features_api(api, run_id) -> None:
    client, _ = api
    payload = client.get(f"/api/runs/{run_id}/features").json()
    assert len(payload["features"]) == 8
    detail = client.get(f"/api/runs/{run_id}/features/PA-VEH-01").json()
    assert detail["feature"]["feature_id"] == "PA-VEH-01"
    assert detail["feature"]["evidence_ids"]


def test_metrics_and_packet_api(api, run_id) -> None:
    client, _ = api
    metrics = client.get(f"/api/runs/{run_id}/metrics").json()
    assert [m["metric_id"] for m in metrics["metrics"]] == ["M1", "M2", "M3", "M4", "M5", "M6"]
    packet = client.get(f"/api/runs/{run_id}/packet").json()
    assert len(packet["pages"]) == 6


def test_evaluation_summary_strip_and_charts(api, run_id) -> None:
    client, _ = api
    text = client.get(f"/evaluation?run={run_id}").text
    assert 'data-eval-summary' in text
    for fact in [
        "estimate-moving issues",
        "finding F1",
        "holdout recall (not imported)",
        "top-8 allowance",
        "hard negatives silent",
        "all metrics in-sample on one synthetic fixture",
    ]:
        assert fact in text, fact
    assert "6/6" in text
    assert "48/48" in text
    assert "4/4" in text
    assert "6/8" in text
    assert "24/24" in text
    assert 'data-chart="wilson"' in text
    assert 'data-chart="baseline-bars"' in text
    for metric_id in ["M1", "M2", "M3", "M4", "M5", "M6"]:
        assert f'data-metric-id="{metric_id}"' in text
    for metric_id in ["M1", "M4", "M6"]:
        assert f'data-bar-metric="{metric_id}"' in text
    assert "95% Wilson intervals" in text
    assert "What this does not prove" in text
    assert "not imported" in text
    assert "metric-fact-allowance" in text
    assert 'href="#limitations"' in text
    assert 'id="limitations"' in text


def test_workbench_legend_caption_and_all_six_columns(api, run_id) -> None:
    client, _ = api
    text = client.get(f"/?run={run_id}&feature=PA-VEH-01").text
    assert 'class="spine-caption"' in text
    for label in ["PCF", "Entity", "Typelist", "Template / Gosu", "API draft", "Tests"]:
        assert f'data-column-label="{label}"' in text, label
    for kind in ["contains", "declares", "references", "configures", "tested_by"]:
        assert f"legend-{kind}" in text, kind
    assert "selected node" in text
    assert "data-spine-scroll-hint" in text
    assert "Spine table fallback" in text


def test_findings_table_columns_caption_and_source_title(api, run_id) -> None:
    client, _ = api
    text = client.get(f"/findings?run={run_id}&selected=F-008").text
    assert '<caption class="table-caption">' in text
    for header in ["Rule", "Title", "Source", "Severity", "Claim strength", "Standard", "State"]:
        assert f'<th scope="col">{header}</th>' in text, header
    assert 'class="table-scroll"' in text
    assert 'class="source-cell"' in text
    assert "gsrc/acme/integration/LegacyVehicleServlet.gs:3" in text


def test_workbench_direct_evidence_url_selects_node(api, run_id) -> None:
    client, _ = api
    features = client.get(f"/api/runs/{run_id}/features").json()["features"]
    feature = features[0]
    evidence = client.get(f"/api/runs/{run_id}/features/{feature['feature_id']}").json()["evidence"]
    target = next(item for item in evidence if item["evidence_id"] == "EV-0006")
    text = client.get(f"/?run={run_id}&feature={feature['feature_id']}&evidence={target['evidence_id']}").text
    assert "node-artifact selected" in text
    assert 'aria-pressed="true"' in text
    assert "Selected node evidence" in text
    assert target["path"] in text


def test_decision_persists_and_is_audited(api, run_id) -> None:
    client, token = api
    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json={
            "object_type": "mapping", "object_id": "M-12", "action": "reject",
            "reason": "Typelist enum requires reviewer confirmation",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["assumption"]["assumption_id"].startswith("A-DEC-")
    assert payload["assumption"]["related_mapping_id"] == "M-12"
    mappings = client.get(f"/api/runs/{run_id}/mappings").json()["mappings"]
    rejected = next(m for m in mappings if m["mapping_id"] == "M-12")
    assert rejected["reviewer_state"] == "rejected"
    assumptions = client.get(f"/api/runs/{run_id}/assumptions").json()["assumptions"]
    assert any("M-12" in a["statement"] or a["related_mapping_id"] == "M-12" for a in assumptions)
    audit = client.get(f"/api/runs/{run_id}/audit").json()
    assert audit["verified"] is True
    assert any(e["action"] == "mapping.reject" for e in audit["events"])


def test_change_decision_returns_and_persists_visible_state(api, run_id) -> None:
    client, token = api
    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json={"object_type": "change", "object_id": "C-01", "action": "accept",
              "reason": "Diff reviewed against the local contract"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    assert response.json()["object"]["approval_state"] == "accepted"
    changes = client.get(f"/reconstruction?run={run_id}&tab=draft")
    assert "accepted" in changes.text


def test_rerun_without_force_reuses_run(api, run_id) -> None:
    client, token = api
    response = client.post(
        "/api/runs",
        json={"project_id": "demo", "fixture_id": "demo-slice-300", "force": False},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    assert response.json()["run_id"] == run_id


def test_csrf_is_required(api, run_id) -> None:
    client, _ = api
    response = client.post(
        f"/api/runs/{run_id}/decisions",
        json={"object_type": "mapping", "object_id": "M-01", "action": "accept", "reason": "x"},
    )
    assert response.status_code == 403


def test_assistant_refuses_without_evidence(api, run_id) -> None:
    client, token = api
    response = client.post(
        f"/api/runs/{run_id}/assistant",
        json={"question": "Does this estate use territory rating?"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["grounded"] is False
    assert "cannot determine" in answer["answer"].lower()


def test_csp_header_present(api, run_id) -> None:
    client, _ = api
    response = client.get(f"/?run={run_id}")
    csp = response.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp


def test_source_untouched(api, run_id) -> None:
    client, _ = api
    manifest = client.get(f"/api/runs/{run_id}/manifest?page=1&size=1").json()
    assert snapshot_hash(DEMO) == manifest["snapshot_hash"]




def test_zip_snapshot_import(api, tmp_path) -> None:
    import zipfile

    client, token = api
    archive = tmp_path / "demo.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(DEMO.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(DEMO).as_posix())
    import time

    with archive.open("rb") as fh:
        started = time.perf_counter()
        response = client.post(
            "/api/imports",
            files={"file": ("demo.zip", fh, "application/zip")},
            headers={"X-CSRF-Token": token},
        )
        elapsed = time.perf_counter() - started
    assert response.status_code == 200, response.text
    assert elapsed < 10.0, f"300-file import took {elapsed:.2f}s"
    run_id = response.json()["run_id"]
    status = client.get(f"/api/runs/{run_id}/status").json()
    assert status["status"] == "succeeded"
    features = client.get(f"/api/runs/{run_id}/features").json()["features"]
    assert len(features) == 8
    assert client.post(f"/api/runs/{run_id}/delete", headers={"X-CSRF-Token": token}).status_code == 200


def test_missing_run_pages_return_scoped_404(api) -> None:
    client, _ = api
    for path in ["/manifest", "/reconstruction", "/findings", "/evaluation", "/packet"]:
        response = client.get(f"{path}?run=R-NOPE")
        assert response.status_code == 404, path
        assert "no longer exists" in response.text


def test_manifest_excluded_filter_matches_banner(api, run_id) -> None:
    client, _ = api
    payload = client.get(f"/api/runs/{run_id}/manifest?page=1&size=500").json()
    excluded_paths = payload["unsupported_paths"]
    assert len(excluded_paths) == 4
    response = client.get(f"/manifest?run={run_id}&excluded=1")
    assert response.status_code == 200
    text = response.text
    assert "4 matching (excluded files)" in text
    for path in excluded_paths:
        assert path in text, path
    assert "2 binary" in text
    assert "1 corrupt" in text
    assert "1 unsupported" in text
    assert "Source unchanged." in text
    # The Workbench banner now points at the complete excluded view.
    workbench = client.get(f"/?run={run_id}&feature=PA-VEH-01").text
    assert f"/manifest?run={run_id}&excluded=1" in workbench


def test_every_feature_opens_with_a_spine(api, run_id) -> None:
    client, _ = api
    features = client.get(f"/api/runs/{run_id}/features").json()["features"]
    assert len(features) == 8
    for feature in features:
        response = client.get(f"/?run={run_id}&feature={feature['feature_id']}")
        assert response.status_code == 200, feature["feature_id"]
        assert "No spine has been generated for this feature yet." not in response.text
        assert "spine-node" in response.text
        assert feature["feature_id"] in response.text


def test_findings_claim_classes_and_source_location(api, run_id) -> None:
    client, _ = api
    response = client.get(f"/findings?run={run_id}&selected=F-005")
    text = response.text
    assert response.status_code == 200
    assert "pill pill-claim claim-verified-policy" in text
    assert "pill pill-claim claim-heuristic" in text
    assert "gsrc/acme/integration/LegacyVehicleServlet.gs:3" in text
    assert "Query.make" in text
    assert "Precision guards" in text


def test_findings_standard_fallback_without_standard_id(api, run_id) -> None:
    client, _ = api
    text = client.get(f"/findings?run={run_id}&selected=F-023").text
    assert "c_correcting_compile_errors.html" in text
    assert "public reference" in text
    assert "Standard" in text


def test_findings_selected_route_preserves_detail(api, run_id) -> None:
    client, _ = api
    response = client.get(f"/findings?run={run_id}&selected=F-008")
    assert response.status_code == 200
    assert '<tr class="selected" data-finding-row="F-008">' in response.text
    assert "Hidden or internal package reference" in response.text


def test_unknown_reconstruction_tab_falls_back_to_mappings(api, run_id) -> None:
    client, _ = api
    response = client.get(f"/reconstruction?run={run_id}&tab=not-a-tab")
    assert response.status_code == 200
    assert '<section class="tab-panel active" data-tab-panel="mappings">' in response.text
    assert '<section class="tab-panel active" data-tab-panel="not-a-tab">' not in response.text


def test_import_affordance_renders(api) -> None:
    client, _ = api
    response = client.get("/import")
    assert response.status_code == 200
    assert "Import 300-file demo slice" in response.text
    runs = client.get("/runs")
    assert 'href="/import"' in runs.text


def test_packet_audit_head_matches_current_log(api, run_id) -> None:
    client, token = api
    client.post(
        f"/api/runs/{run_id}/decisions",
        json={"object_type": "mapping", "object_id": "M-02", "action": "defer",
              "reason": "Needs more evidence"},
        headers={"X-CSRF-Token": token},
    )
    audit = client.get(f"/api/runs/{run_id}/audit").json()
    packet = client.get(f"/api/runs/{run_id}/packet").json()
    assert packet["hashes"]["audit_head"] == audit["events"][-1]["hash"]


def test_holdout_is_not_importable(api) -> None:
    client, token = api
    response = client.post(
        "/api/runs",
        json={"project_id": "demo", "fixture_id": "northstar-pc-2026.10", "force": True},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 400




def test_running_run_shows_loading_state(api) -> None:
    client, _ = api
    store = client.app.state.store
    store.create_run("R-LOADING", project_id="demo", snapshot_id="S-LOADING", fixture_id="demo-slice-300")
    store.update_status("R-LOADING", status="running", stage="parse", percent=40.0)
    response = client.get("/manifest?run=R-LOADING")
    assert response.status_code == 200
    assert "Analysis in progress" in response.text
    assert "data-run-wait" in response.text


def test_runs_page_lists_existing_run(api, run_id) -> None:
    client, _ = api
    response = client.get("/runs")
    assert response.status_code == 200
    assert "<h1>Runs</h1>" in response.text
    assert run_id in response.text
    assert "data-runs-empty" in response.text
    assert 'href="/import"' in response.text


def test_failed_run_shows_scoped_error(api) -> None:
    client, _ = api
    store = client.app.state.store
    store.create_run("R-FAILED", project_id="demo", snapshot_id="S-FAILED", fixture_id="demo-slice-300")
    store.update_status("R-FAILED", status="failed", stage="failed", percent=0.0,
                        error={"code": "ParseError", "message": "Synthetic failure for test", "retryable": False})
    for path in ["/", "/manifest", "/reconstruction", "/findings", "/evaluation", "/packet"]:
        response = client.get(f"{path}?run=R-FAILED")
        assert response.status_code == 200, path
        assert "Synthetic failure for test" in response.text, path
    response = client.get("/?run=R-FAILED")
    assert "Analysis did not complete" in response.text


def test_packet_refresh_preserves_readiness_and_run_context(api, run_id) -> None:
    client, _ = api
    status = client.get(f"/api/runs/{run_id}/status").json()
    assert status["release_context"]
    assert status["reference_path"].endswith("pa_veh_01_reference.json")
    packet = client.get(f"/api/runs/{run_id}/packet").json()
    assert packet["counts"]["readiness"] >= 1
    page = client.get(f"/packet?run={run_id}").text
    assert status["release_context"] in page


def test_packet_refresh_failure_is_visible_and_export_blocks(api, run_id, monkeypatch) -> None:
    client, _ = api

    def fail_build(**kwargs):
        raise RuntimeError("synthetic refresh failure")

    monkeypatch.setattr("app.main.build_packet", fail_build)
    page = client.get(f"/packet?run={run_id}")
    assert page.status_code == 200
    assert "Packet refresh failed; this artifact may be stale" in page.text
    assert "synthetic refresh failure" in page.text
    export = client.get(f"/packet/export?run={run_id}")
    assert export.status_code == 503
    assert "refusing to export a stale artifact" in export.json()["detail"]


def test_delete_run(api, run_id) -> None:
    client, token = api
    response = client.post(f"/api/runs/{run_id}/delete", headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    assert client.get(f"/api/runs/{run_id}/status").status_code == 404


def test_fallback_spine_covers_inventory_evidence_for_old_runs() -> None:
    from app.views import _fallback_spine

    spine = _fallback_spine(
        {"feature_id": "PA-DRV-01", "evidence_ids": ["EV-1", "EV-1", "EV-2", "EV-3"]},
        {
            "EV-1": {"path": "config/web/pcf/auto/DriverDV.pcf", "confidence": "parsed"},
            "EV-2": {"path": "config/metadata/entity/Driver.eti", "confidence": "parsed"},
            "EV-3": {"path": "gtest/acme/DriverTest.gs", "confidence": "linked"},
        },
    )
    assert len(spine.nodes) == 3
    assert {node.kind for node in spine.nodes} == {"artifact", "test"}


def test_every_page_renders_without_a_run(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "empty-data",
        fixtures_dir=REPO / "fixtures",
        secret_key="test-secret",
        sync_runs=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        for path in [
            "/", "/manifest", "/reconstruction", "/findings", "/evaluation", "/packet",
            "/runs", "/import", "/about", "/settings",
        ]:
            response = client.get(path)
            assert response.status_code == 200, path
            assert "PreFlight" in response.text, path


def test_settings_page_content(api) -> None:
    client, _ = api
    response = client.get("/settings")
    assert response.status_code == 200
    assert "Review context" in response.text
    assert "Data policy" in response.text
    assert "holdout locked" in response.text


# -- decision integrity, run guards, deletion and corruption ----------------

def _synthetic_run(client, run_id: str, *, mappings: list[dict] | None = None,
                   changes: list[dict] | None = None,
                   findings: list[dict] | None = None,
                   status: str = "succeeded") -> RunStore:
    """Create a small valid run without paying for the full pipeline."""
    store: RunStore = client.app.state.store
    store.create_run(run_id, fixture_id="demo-slice-300")
    if mappings is not None:
        store.write_artifact(run_id, "mappings.json",
                             {"schema_version": "1.0", "mappings": mappings})
    if changes is not None:
        store.write_artifact(run_id, "changes.json",
                             {"schema_version": "1.0", "changes": changes})
    if findings is not None:
        store.write_artifact(run_id, "findings.json",
                             {"schema_version": "1.0", "findings": findings,
                              "readiness": []})
    if status == "queued":
        return store
    store.update_status(
        run_id, status=status, stage=status, percent=100.0 if status == "succeeded" else 40.0,
        error=None if status != "failed" else {"code": "ParseError", "message": "synthetic"},
    )
    return store


def _post_decision(client, token: str, run_id: str, object_type: str, object_id: str,
                   action: str, *, edited_value: str | None = None, reason: str = "reviewed"):
    body = {"object_type": object_type, "object_id": object_id,
            "action": action, "reason": reason}
    if edited_value is not None:
        body["edited_value"] = edited_value
    return client.post(f"/api/runs/{run_id}/decisions", json=body,
                       headers={"X-CSRF-Token": token})


def test_decision_state_machine_and_idempotency(api) -> None:
    client, token = api
    run_id = "R-STATE-MACHINE"
    store = _synthetic_run(
        client, run_id,
        mappings=[{"mapping_id": f"M-{i}", "target_name": "Old"} for i in range(1, 5)],
        changes=[{"change_id": f"C-{i}", "approval_state": "pending"} for i in range(1, 4)],
        findings=[{"finding_id": f"F-{i}", "decision": "open"} for i in range(1, 4)],
    )

    first = _post_decision(client, token, run_id, "mapping", "M-1", "accept")
    assert first.status_code == 200, first.text
    first_decision_id = first.json()["decision"]["decision_id"]
    decisions_before = len(store.read_artifact(run_id, "decisions.json")["decisions"])
    audit_before = len(store.read_audit(run_id))

    duplicate = _post_decision(client, token, run_id, "mapping", "M-1", "accept")
    assert duplicate.status_code == 200
    assert duplicate.json()["idempotent"] is True
    assert duplicate.json()["decision"]["decision_id"] == first_decision_id
    assert len(store.read_artifact(run_id, "decisions.json")["decisions"]) == decisions_before
    assert len(store.read_audit(run_id)) == audit_before

    conflict = _post_decision(client, token, run_id, "mapping", "M-1", "reject")
    assert conflict.status_code == 409
    assert "already 'accepted'" in conflict.json()["detail"]
    assert len(store.read_audit(run_id)) == audit_before

    assert _post_decision(client, token, run_id, "mapping", "M-2", "edit").status_code == 400
    edit = _post_decision(client, token, run_id, "mapping", "M-2", "edit", edited_value="New")
    assert edit.status_code == 200, edit.text
    assert edit.json()["object"]["target_name"] == "New"
    assert edit.json()["object"]["reviewer_state"] == "edited"
    edit_again = _post_decision(client, token, run_id, "mapping", "M-2", "edit",
                                edited_value="Different")
    assert edit_again.status_code == 200
    assert edit_again.json()["idempotent"] is True
    assert edit_again.json()["object"]["target_name"] == "New"

    reject = _post_decision(client, token, run_id, "mapping", "M-3", "reject")
    assert reject.status_code == 200
    assumption_id = reject.json()["assumption"]["assumption_id"]
    reject_again = _post_decision(client, token, run_id, "mapping", "M-3", "reject")
    assert reject_again.status_code == 200
    assert reject_again.json()["idempotent"] is True
    assert reject_again.json()["assumption"]["assumption_id"] == assumption_id
    assumptions = store.read_artifact(run_id, "assumptions.json")["assumptions"]
    assert len([a for a in assumptions if a["related_mapping_id"] == "M-3"]) == 1

    assert _post_decision(client, token, run_id, "mapping", "M-4", "defer").status_code == 200
    assert _post_decision(client, token, run_id, "mapping", "M-4", "accept").status_code == 409

    change = _post_decision(client, token, run_id, "change", "C-1", "accept")
    assert change.status_code == 200
    assert _post_decision(client, token, run_id, "change", "C-1", "accept").json()["idempotent"] is True
    assert _post_decision(client, token, run_id, "change", "C-1", "reject").status_code == 409

    defer_change = _post_decision(client, token, run_id, "change", "C-2", "defer")
    assert defer_change.status_code == 200
    assert _post_decision(client, token, run_id, "change", "C-2", "defer").json()["idempotent"] is True
    assert _post_decision(client, token, run_id, "change", "C-2", "accept").status_code == 409

    finding = _post_decision(client, token, run_id, "finding", "F-1", "accept")
    assert finding.status_code == 200
    assert _post_decision(client, token, run_id, "finding", "F-1", "accept").json()["idempotent"] is True
    assert _post_decision(client, token, run_id, "finding", "F-1", "reject").status_code == 409

    assert _post_decision(client, token, run_id, "finding", "F-2", "edit").status_code == 400
    finding_edit = _post_decision(
        client, token, run_id, "finding", "F-2", "edit", edited_value="Reclassified"
    )
    assert finding_edit.status_code == 200, finding_edit.text
    assert finding_edit.json()["object"]["decision"] == "accepted"
    assert "Reclassified" in finding_edit.json()["decision"]["reason"]
    assert _post_decision(
        client, token, run_id, "finding", "F-2", "edit", edited_value="Again"
    ).json()["idempotent"] is True

    assert store.verify_audit(run_id) is True


def test_run_status_guards_cancel_and_delete(api) -> None:
    client, token = api
    store = _synthetic_run(client, "R-GUARD-QUEUED",
                           mappings=[{"mapping_id": "M-1"}], status="queued")
    response = _post_decision(client, token, "R-GUARD-QUEUED", "mapping", "M-1", "accept")
    assert response.status_code == 409
    assert "succeeded" in response.json()["detail"]
    assert client.get("/api/runs/R-GUARD-QUEUED/packet").status_code == 409

    cancel = client.post("/api/runs/R-GUARD-QUEUED/cancel", headers={"X-CSRF-Token": token})
    assert cancel.status_code == 200
    assert store.read_status("R-GUARD-QUEUED")["status"] == "cancelled"
    assert any(e["action"] == "run.cancelled" for e in store.read_audit("R-GUARD-QUEUED"))
    assert _post_decision(
        client, token, "R-GUARD-QUEUED", "mapping", "M-1", "accept"
    ).status_code == 409

    _synthetic_run(client, "R-GUARD-RUNNING",
                   mappings=[{"mapping_id": "M-1"}], status="running")
    assert _post_decision(
        client, token, "R-GUARD-RUNNING", "mapping", "M-1", "accept"
    ).status_code == 409
    assert client.post("/api/runs/R-GUARD-RUNNING/cancel",
                       headers={"X-CSRF-Token": token}).status_code == 200
    assert store.read_status("R-GUARD-RUNNING")["status"] == "cancelled"

    _synthetic_run(client, "R-GUARD-FAILED",
                   mappings=[{"mapping_id": "M-1"}], status="failed")
    assert _post_decision(
        client, token, "R-GUARD-FAILED", "mapping", "M-1", "accept"
    ).status_code == 409
    assert client.post("/api/runs/R-GUARD-FAILED/delete",
                       headers={"X-CSRF-Token": token}).status_code == 200
    assert client.get("/api/runs/R-GUARD-FAILED/status").status_code == 404


def test_startup_reconciliation_cancels_stuck_runs(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "reconciled-data",
        fixtures_dir=REPO / "fixtures",
        secret_key="test-secret",
        sync_runs=True,
    )
    store = RunStore(settings.data_dir)
    for run_id, status in (("R-STUCK-QUEUED", "queued"), ("R-STUCK-RUNNING", "running")):
        store.create_run(run_id)
        if status == "running":
            store.update_status(run_id, status="running", stage="parse", percent=30.0)

    create_app(settings)

    for run_id in ("R-STUCK-QUEUED", "R-STUCK-RUNNING"):
        payload = store.read_status(run_id)
        assert payload["status"] == "cancelled"
        assert payload["error"]["code"] == "RunInterrupted"
        events = store.read_audit(run_id)
        cancelled = [e for e in events if e["action"] == "run.cancelled"]
        assert len(cancelled) == 1
        assert "startup" in cancelled[0]["reason"]
        assert store.verify_audit(run_id) is True


def test_delete_during_run_cannot_resurrect_directory(api) -> None:
    client, token = api
    store: RunStore = client.app.state.store
    app = client.app
    run_id = "R-DELETE-RUNNING"
    store.create_run(run_id)
    store.update_status(run_id, status="running", stage="parse", percent=25.0)

    cancel = threading.Event()
    allow_stale_write = threading.Event()
    started = threading.Event()
    errors: list[str] = []
    app.state.cancel_events[run_id] = cancel

    def stale_worker() -> None:
        started.set()
        cancel.wait(5)
        # Simulate a pipeline reaching its finally block, then writing late.
        app.state.cancel_events.pop(run_id, None)
        allow_stale_write.wait(5)
        try:
            store.write_artifact(run_id, "features.json", {"features": []})
        except StoreError as exc:
            errors.append(exc.code)

    thread = threading.Thread(target=stale_worker)
    thread.start()
    assert started.wait(2)
    response = client.post(f"/api/runs/{run_id}/delete", headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.text
    allow_stale_write.set()
    thread.join(5)

    assert errors == ["RUN_DELETED"]
    assert not store.run_dir(run_id).exists()
    assert client.get(f"/api/runs/{run_id}/status").status_code == 404


def test_overlong_run_id_is_rejected_without_500(api) -> None:
    client, token = api
    long_id = "R-" + "a" * 300
    assert client.get(f"/api/runs/{long_id}/status").status_code == 404
    response = client.post(
        f"/api/runs/{long_id}/decisions",
        json={"object_type": "mapping", "object_id": "M-1",
              "action": "accept", "reason": "x"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 404
    assert client.get(f"/?run={long_id}").status_code == 404


@pytest.mark.parametrize("artifact", ["features.json", "mappings.json"])
def test_corrupt_core_artifact_returns_corrupt_code(tmp_path: Path, artifact: str) -> None:
    settings = Settings(
        data_dir=tmp_path / "corrupt-data",
        fixtures_dir=REPO / "fixtures",
        secret_key="test-secret",
        sync_runs=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        token = re.search(
            r'name="csrf-token" content="([^"]+)"', client.get("/about").text
        ).group(1)
        store: RunStore = app.state.store
        run_id = f"R-CORRUPT-{artifact.split('.')[0]}"
        store.create_run(run_id)
        store.write_artifact(run_id, "features.json",
                             {"schema_version": "1.0", "features": []})
        store.write_artifact(run_id, "mappings.json",
                             {"schema_version": "1.0",
                              "mappings": [{"mapping_id": "M-1", "target_name": "Old"}]})
        (store.run_dir(run_id) / artifact).write_text("{not json", encoding="utf-8")
        store.update_status(run_id, status="succeeded", stage="succeeded", percent=100.0)

        endpoint = artifact.split(".")[0]
        api_response = client.get(f"/api/runs/{run_id}/{endpoint}")
        assert api_response.status_code == 500
        assert api_response.json()["error"]["code"] == "CORRUPT_ARTIFACT"

        page = client.get(f"/?run={run_id}")
        assert page.status_code == 500
        assert page.json()["error"]["code"] == "CORRUPT_ARTIFACT"

        decision = _post_decision(client, token, run_id, "mapping", "M-1", "accept")
        assert decision.status_code == 500
        assert decision.json()["error"]["code"] == "CORRUPT_ARTIFACT"


def test_missing_optional_artifact_still_defaults(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "optional-data",
        fixtures_dir=REPO / "fixtures",
        secret_key="test-secret",
        sync_runs=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        store: RunStore = app.state.store
        run_id = "R-OPTIONAL"
        store.create_run(run_id)
        store.write_artifact(run_id, "features.json",
                             {"schema_version": "1.0", "features": []})
        store.write_artifact(run_id, "mappings.json",
                             {"schema_version": "1.0", "mappings": []})
        store.update_status(run_id, status="succeeded", stage="succeeded", percent=100.0)
        assert client.get(f"/api/runs/{run_id}/metrics").json() == {
            "metrics": [], "supporting": []
        }
        assert client.get(f"/?run={run_id}").status_code == 200


def test_concurrent_mapping_accepts_persist_every_decision(api) -> None:
    from concurrent.futures import ThreadPoolExecutor

    client, token = api
    run_id = "R-CONCURRENT-ACCEPTS"
    mapping_ids = [f"M-{index:02d}" for index in range(1, 13)]
    store = _synthetic_run(
        client, run_id,
        mappings=[{"mapping_id": mapping_id, "target_name": "Old"}
                  for mapping_id in mapping_ids],
    )

    def decide(mapping_id: str):
        return _post_decision(client, token, run_id, "mapping", mapping_id, "accept")

    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(decide, mapping_ids))

    assert [response.status_code for response in responses] == [200] * 12
    mappings = store.read_artifact(run_id, "mappings.json")["mappings"]
    assert {m["mapping_id"]: m["reviewer_state"] for m in mappings} == {
        mapping_id: "accepted" for mapping_id in mapping_ids
    }
    decisions = store.read_artifact(run_id, "decisions.json")["decisions"]
    assert len(decisions) == 12
    events = store.read_audit(run_id)
    assert len(events) == 12
    assert [event["seq"] for event in events] == list(range(12))
    assert [event["action"] for event in events] == ["mapping.accept"] * 12
    assert len({event["event_id"] for event in events}) == 12
    assert len({event["prev_hash"] for event in events}) == 12
    assert store.verify_audit(run_id) is True


def test_delete_waits_for_direct_draft_writer(tmp_path: Path, monkeypatch) -> None:
    """A worker writing files directly (not through RunStore) must not resurrect."""
    import time

    settings = Settings(
        data_dir=tmp_path / "delete-worker-data",
        fixtures_dir=REPO / "fixtures",
        secret_key="test-secret",
        sync_runs=False,
    )

    def slow_direct_writer(fixture, store, run_id, **kwargs):
        time.sleep(0.3)
        draft = store.run_dir(run_id) / "draft"
        draft.mkdir(parents=True, exist_ok=True)
        (draft / "late.txt").write_text("late direct write", encoding="utf-8")

    monkeypatch.setattr("app.main.execute_run", slow_direct_writer)
    app = create_app(settings)
    with TestClient(app) as client:
        token = re.search(
            r'name="csrf-token" content="([^"]+)"', client.get("/about").text
        ).group(1)
        created = client.post(
            "/api/runs",
            json={"fixture_id": "demo-slice-300", "force": True},
            headers={"X-CSRF-Token": token},
        )
        assert created.status_code == 200, created.text
        run_id = created.json()["run_id"]
        deleted = client.post(f"/api/runs/{run_id}/delete",
                              headers={"X-CSRF-Token": token})
        assert deleted.status_code == 200, deleted.text
        # The worker had time to finish its direct write before deletion; the
        # joined worker cannot recreate the directory afterwards.
        assert not app.state.store.run_dir(run_id).exists()
        assert client.get(f"/api/runs/{run_id}/status").status_code == 404
