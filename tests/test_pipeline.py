"""End-to-end pipeline test (no HTTP): artifacts, audit, metrics, packet.

Written before app/services/pipeline.py exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.intake import snapshot_hash
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
