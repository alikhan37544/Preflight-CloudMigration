"""Run-store contract tests: atomic writes, artifact access, audit chain.

Written before app/store.py exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.store import RunStore, StoreError


@pytest.fixture()
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / "data")


def test_create_run_and_read_artifact(store: RunStore) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "manifest.json", {"file_count": 3})
    assert store.read_artifact("R-1", "manifest.json") == {"file_count": 3}
    assert (store.run_dir("R-1") / "manifest.json").is_file()


def test_atomic_write_leaves_no_tmp_files(store: RunStore) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "features.json", {"a": 1})
    leftovers = list(store.run_dir("R-1").glob("*.tmp"))
    assert leftovers == []


def test_path_traversal_is_rejected(store: RunStore) -> None:
    store.create_run("R-1")
    for name in ["../evil.json", "/etc/passwd", "a/../../evil.json"]:
        with pytest.raises(StoreError):
            store.write_artifact("R-1", name, {"x": 1})
        with pytest.raises(StoreError):
            store.read_artifact("R-1", name)


def test_audit_chain_verifies(store: RunStore) -> None:
    store.create_run("R-1")
    store.append_audit("R-1", action="run.created", object_type="run", object_id="R-1")
    store.append_audit("R-1", action="mapping.accepted", object_type="mapping", object_id="M-1")
    store.append_audit("R-1", action="mapping.rejected", object_type="mapping", object_id="M-2")
    assert store.verify_audit("R-1") is True
    events = store.read_audit("R-1")
    assert [e["seq"] for e in events] == [0, 1, 2]
    assert events[0]["prev_hash"] == "GENESIS"
    assert events[1]["prev_hash"] == events[0]["hash"]


def test_audit_chain_detects_tampering(store: RunStore) -> None:
    store.create_run("R-1")
    store.append_audit("R-1", action="run.created", object_type="run", object_id="R-1")
    store.append_audit("R-1", action="mapping.accepted", object_type="mapping", object_id="M-1")
    audit_path = store.run_dir("R-1") / "audit.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    event["action"] = "run.deleted"
    lines[0] = json.dumps(event)
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert store.verify_audit("R-1") is False


def test_record_decision_updates_state_and_audit(store: RunStore) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "decisions.json", {"decisions": []})
    decision = store.record_decision(
        "R-1",
        object_type="mapping",
        object_id="M-1",
        action="accept",
        actor="reviewer",
        reason="Verified against public docs",
    )
    assert decision["action"] == "accept"
    decisions = store.read_artifact("R-1", "decisions.json")
    assert len(decisions["decisions"]) == 1
    assert store.verify_audit("R-1") is True


def test_delete_run_removes_directory(store: RunStore) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "manifest.json", {"a": 1})
    store.delete_run("R-1")
    assert not store.run_dir("R-1").exists()


def test_list_runs_is_sorted(store: RunStore) -> None:
    store.create_run("R-2")
    store.create_run("R-1")
    assert store.list_runs() == ["R-1", "R-2"]


def test_artifact_allowlist(store: RunStore) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "manifest.json", {"a": 1})
    assert store.read_artifact("R-1", "manifest.json", allowlist={"manifest.json"}) == {"a": 1}
    with pytest.raises(StoreError):
        store.read_artifact("R-1", "manifest.json", allowlist={"features.json"})


def test_run_status_roundtrip(store: RunStore) -> None:
    store.create_run("R-1")
    store.update_status("R-1", status="running", stage="parse", percent=20.0)
    status = store.read_status("R-1")
    assert status["status"] == "running"
    assert status["stage"] == "parse"
    assert status["progress"]["percent"] == 20.0
