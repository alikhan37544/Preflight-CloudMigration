"""API and product-shell tests: routes, CSRF, decisions, assistant, immutability.

Written before app/main.py exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.intake import snapshot_hash

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
