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


# -- concurrency and atomic-write hardening --------------------------------


def test_atomic_write_temp_names_are_unique(store: RunStore, monkeypatch) -> None:
    import app.store as store_module

    store.create_run("R-1")
    seen = []
    real_mkstemp = store_module.tempfile.mkstemp

    def spy(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        seen.append(Path(name))
        return fd, name

    monkeypatch.setattr(store_module.tempfile, "mkstemp", spy)
    store.write_artifact("R-1", "features.json", {"n": 1})
    store.write_artifact("R-1", "features.json", {"n": 2})
    assert len(seen) == 2
    assert len(set(seen)) == 2
    assert all(path.parent == store.run_dir("R-1") for path in seen)
    assert store.read_artifact("R-1", "features.json") == {"n": 2}


def test_concurrent_status_updates_leave_valid_json(store: RunStore) -> None:
    from concurrent.futures import ThreadPoolExecutor

    store.create_run("R-1")

    def update(index: int) -> None:
        store.update_status(
            "R-1", status="running", stage=f"s{index}", percent=float(index % 101)
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(update, range(40)))
    status = store.read_status("R-1")
    assert status["status"] == "running"
    assert 0.0 <= status["progress"]["percent"] <= 100.0


def test_concurrent_appends_produce_a_valid_chain(store: RunStore) -> None:
    from concurrent.futures import ThreadPoolExecutor

    store.create_run("R-1")
    other = RunStore(store.base_dir)  # same directory, different instance

    def append(index: int) -> None:
        writer = store if index % 2 else other
        writer.append_audit(
            "R-1", action="mapping.reviewed", object_type="mapping",
            object_id=f"M-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(48)))

    events = store.read_audit("R-1")
    assert [event["seq"] for event in events] == list(range(48))
    assert len({event["event_id"] for event in events}) == 48
    assert store.verify_audit("R-1") is True


# -- audit verification: checkpoint, truncation, cross-run -----------------


def test_audit_checkpoint_tracks_count_and_head(store: RunStore) -> None:
    store.create_run("R-1")
    store.append_audit("R-1", action="run.created", object_type="run", object_id="R-1")
    second = store.append_audit(
        "R-1", action="mapping.accepted", object_type="mapping", object_id="M-1"
    )
    checkpoint = store.read_artifact("R-1", "audit.checkpoint.json")
    assert checkpoint["run_id"] == "R-1"
    assert checkpoint["count"] == 2
    assert checkpoint["head"] == second["hash"]


def test_verify_audit_detects_tail_truncation(store: RunStore) -> None:
    store.create_run("R-1")
    for index in range(3):
        store.append_audit(
            "R-1", action="mapping.reviewed", object_type="mapping",
            object_id=f"M-{index}",
        )
    audit_path = store.run_dir("R-1") / "audit.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    audit_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    assert store.verify_audit("R-1") is False


def test_verify_audit_detects_cross_run_copy(store: RunStore) -> None:
    store.create_run("R-1")
    store.create_run("R-2")
    for index in range(2):
        store.append_audit(
            "R-1", action="mapping.reviewed", object_type="mapping",
            object_id=f"M-{index}",
        )
        store.append_audit(
            "R-2", action="mapping.reviewed", object_type="mapping",
            object_id=f"M-{index}",
        )
    # Copy both the log and its checkpoint: the chain itself is valid, but the
    # events belong to R-1 and must not verify as R-2.
    for name in ("audit.jsonl", "audit.checkpoint.json"):
        (store.run_dir("R-2") / name).write_bytes(
            (store.run_dir("R-1") / name).read_bytes()
        )
    assert store.verify_audit("R-2") is False


def test_verify_audit_without_checkpoint_is_backward_compatible(store: RunStore) -> None:
    store.create_run("R-1")
    store.append_audit("R-1", action="run.created", object_type="run", object_id="R-1")
    (store.run_dir("R-1") / "audit.checkpoint.json").unlink()
    assert store.verify_audit("R-1") is True


# -- decision/audit consistency and corrupt reads ---------------------------


def test_record_decision_does_not_persist_when_audit_fails(store: RunStore, monkeypatch) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "decisions.json", {"decisions": []})

    def fail(*args, **kwargs):
        raise OSError("audit unavailable")

    monkeypatch.setattr(store, "append_audit", fail)
    with pytest.raises(OSError):
        store.record_decision(
            "R-1", object_type="mapping", object_id="M-1", action="accept",
            actor="reviewer", reason="test",
        )
    assert store.read_artifact("R-1", "decisions.json") == {"decisions": []}
    assert store.read_audit("R-1") == []


def test_record_decision_rolls_back_audit_when_decision_write_fails(
    store: RunStore, monkeypatch
) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "decisions.json", {"decisions": []})
    real_atomic_write = store._atomic_write

    def flaky(path: Path, data) -> None:
        if path.name == "decisions.json":
            raise OSError("disk full")
        real_atomic_write(path, data)

    monkeypatch.setattr(store, "_atomic_write", flaky)
    with pytest.raises(OSError):
        store.record_decision(
            "R-1", object_type="mapping", object_id="M-1", action="accept",
            actor="reviewer", reason="test",
        )
    assert store.read_artifact("R-1", "decisions.json") == {"decisions": []}
    assert store.read_audit("R-1") == []
    assert store.verify_audit("R-1") is True


def test_corrupt_status_raises_store_error(store: RunStore) -> None:
    store.create_run("R-1")
    (store.run_dir("R-1") / "status.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(StoreError):
        store.read_status("R-1")


def test_corrupt_artifact_json_raises_store_error(store: RunStore) -> None:
    store.create_run("R-1")
    store.write_artifact("R-1", "manifest.json", "{not json")
    with pytest.raises(StoreError):
        store.read_artifact("R-1", "manifest.json")


def test_corrupt_audit_raises_store_error_and_fails_verification(store: RunStore) -> None:
    store.create_run("R-1")
    (store.run_dir("R-1") / "audit.jsonl").write_text("{not json\n", encoding="utf-8")
    with pytest.raises(StoreError):
        store.read_audit("R-1")
    assert store.verify_audit("R-1") is False


def test_corrupt_decisions_raise_store_error(store: RunStore) -> None:
    store.create_run("R-1")
    (store.run_dir("R-1") / "decisions.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(StoreError):
        store.record_decision(
            "R-1", object_type="mapping", object_id="M-1", action="accept",
            actor="reviewer", reason="test",
        )
