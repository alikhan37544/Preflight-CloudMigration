"""Tests for the optional, evidence-locked AI QCer (no network in tests)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from app.config import Settings
from app.services.ai import AIClient, _validate, run_ai_review
from app.services.pipeline import execute_run
from app.services.migrator import run_migration
from app.store import RunStore

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "fixtures" / "demo-slice-300"
REFERENCE = REPO / "ground_truth" / "reference_target" / "pa_veh_01_reference.json"


@pytest.fixture(scope="module")
def ai_run(tmp_path_factory):
    store = RunStore(tmp_path_factory.mktemp("ai-data"))
    store.create_run("R-AI", project_id="demo", snapshot_id="S-AI")
    execute_run(
        DEMO, store, "R-AI", project_id="demo", fixture_id="demo-slice-300",
        tier="demo", reference_path=REFERENCE,
    )
    run_migration(store, "R-AI", pace=0.0)
    return store


def _valid_payload(store: RunStore) -> dict:
    state = store.read_artifact("R-AI", "migration.json")
    evidence_id = state["packages"][0]["evidence_ids"][0]
    target = state["packages"][0]["target_path"]
    return {
        "summary": [{"text": f"The generated target {target} is supported by the linked record.", "evidence_ids": [evidence_id]}],
        "risks": [{"text": "The open territory assumption still needs an owner.", "severity": "high",
                   "evidence_ids": [evidence_id], "package_id": "WP-01"}],
        "missing_checks": [{"text": "Confirm the target release compiles the generated mapping.", "evidence_ids": [evidence_id]}],
        "critique": [{"package_id": "WP-01", "text": "Validate the generated file against the target release.",
                       "evidence_ids": [evidence_id]}],
    }


class StubClient(AIClient):
    def __init__(self, response: str):
        super().__init__(Settings(ai_provider="none"))
        self.provider = "stub"
        self.model = "stub-1"
        self.base_url = "http://stub.invalid"
        self._response = response

    @property
    def enabled(self) -> bool:
        return True

    def status(self):
        return {"configured": True, "provider": "stub", "model": "stub-1", "reachable": True}

    def chat(self, **kwargs):
        return self._response, {"provider": "stub", "model": "stub-1", "usage": {}}


def test_ai_disabled_by_default() -> None:
    status = AIClient(Settings(ai_provider="none")).status()
    assert status["configured"] is False
    assert "opt-in" in status["reason"]


def test_ai_review_accepts_evidence_locked_output(ai_run) -> None:
    store = ai_run
    client = StubClient(json.dumps(_valid_payload(store)))
    result = run_ai_review(store, "R-AI", client)
    assert result["status"] == "accepted", result
    assert result["validator"]["ok"] is True
    assert result["summary"] and result["risks"]
    assert store.exists("R-AI", "migration/ai-review.json")
    state = store.read_artifact("R-AI", "migration.json")
    assert state["ai"]["status"] == "accepted"
    assert state["ai"]["validator_ok"] is True
    assert any(agent["agent_id"] == "ai-qcer" for agent in state["agents"])


def test_ai_review_rejects_unknown_citation(ai_run) -> None:
    store = ai_run
    payload = _valid_payload(store)
    payload["summary"][0]["evidence_ids"] = ["EV-NOT-IN-RUN"]
    result = run_ai_review(store, "R-AI", StubClient(json.dumps(payload)))
    assert result["status"] == "rejected"
    assert result["validator"]["ok"] is False
    assert any("unknown evidence" in error for error in result["validator"]["errors"])
    assert result["summary"] == []


def test_ai_review_rejects_unknown_path_and_overclaim(ai_run) -> None:
    store = ai_run
    payload = _valid_payload(store)
    payload["summary"][0]["text"] = "Deploy config/integration/secret/target.json after approval."
    result = run_ai_review(store, "R-AI", StubClient(json.dumps(payload)))
    assert result["status"] == "rejected"
    assert result["validator"]["errors"]


def test_ai_review_rejects_malformed_json(ai_run) -> None:
    result = run_ai_review(ai_run, "R-AI", StubClient("not json"))
    assert result["status"] == "rejected"
    assert "valid JSON" in result["validator"]["errors"][0]


def test_ai_validator_rejects_unsupported_number() -> None:
    context = {
        "allowed_evidence_ids": ["EV-1"],
        "allowed_package_ids": ["WP-01"],
        "known_paths": ["config/a.yaml"],
        "packages": [{"package_id": "WP-01"}],
        "evidence": [{"evidence_id": "EV-1"}],
        "gates": [],
        "verification": {},
    }
    ok, errors, _ = _validate({
        "summary": [{"text": "This will take 500 days.", "evidence_ids": ["EV-1"]}],
        "risks": [], "missing_checks": [], "critique": [],
    }, context)
    assert ok is False
    assert any("unsupported number" in error for error in errors)


def test_ai_client_ollama_http_transport() -> None:
    payload = {"summary": [], "risks": [], "missing_checks": [], "critique": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def do_GET(self):
            body = json.dumps({"models": [{"name": "stub:latest"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            assert request["stream"] is False
            body = json.dumps({
                "model": "stub:latest",
                "message": {"content": json.dumps(payload)},
                "eval_count": 12,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = AIClient(Settings(
            ai_provider="ollama",
            ai_model="stub:latest",
            ai_base_url=f"http://127.0.0.1:{server.server_port}",
            ai_timeout=10,
        ))
        assert client.status()["reachable"] is True
        content, meta = client.chat(system="system", user="user")
        assert json.loads(content) == payload
        assert meta["provider"] == "ollama"
        assert meta["eval_count"] == 12
    finally:
        server.shutdown()
        server.server_close()


def test_ai_validator_rejects_readiness_overclaim() -> None:
    context = {
        "allowed_evidence_ids": ["EV-1"],
        "allowed_package_ids": ["WP-01"],
        "allowed_gate_ids": ["G-01"],
        "known_paths": ["config/a.yaml"],
        "known_basenames": ["a.yaml"],
        "packages": [{"package_id": "WP-01"}],
        "evidence": [{"evidence_id": "EV-1"}],
        "gates": [{"gate_id": "G-01"}],
        "verification": {},
    }
    ok, errors, _ = _validate({
        "summary": [{"text": "The draft is ready for deployment.", "evidence_ids": ["EV-1"]}],
        "risks": [], "missing_checks": [], "critique": [],
    }, context)
    assert ok is False
    assert any("overclaim" in error for error in errors)


def test_ai_validator_accepts_known_basename() -> None:
    context = {
        "allowed_evidence_ids": ["EV-1"],
        "allowed_package_ids": ["WP-01"],
        "allowed_gate_ids": ["G-01"],
        "known_paths": ["config/a.yaml"],
        "known_basenames": ["a.yaml"],
        "packages": [{"package_id": "WP-01"}],
        "evidence": [{"evidence_id": "EV-1"}],
        "gates": [{"gate_id": "G-01"}],
        "verification": {},
    }
    ok, errors, clean = _validate({
        "summary": [{"text": "The file a.yaml needs review.", "evidence_ids": ["EV-1"]}],
        "risks": [], "missing_checks": [], "critique": [],
    }, context)
    assert ok is True, errors
    assert clean["summary"][0]["text"] == "The file a.yaml needs review."
