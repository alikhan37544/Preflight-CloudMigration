"""JSON run store with atomic writes and a hash-chained audit log."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

_SAFE_RUN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_ARTIFACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class StoreError(ValueError):
    """Raised for unsafe or missing store operations."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class RunStore:
    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.runs_dir = self.base_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        if not _SAFE_RUN.match(run_id) or ".." in run_id:
            raise StoreError(f"unsafe run id: {run_id!r}")
        return self.runs_dir / run_id

    def _artifact_path(self, run_id: str, name: str, allowlist: Iterable[str] | None = None) -> Path:
        if allowlist is not None and name not in set(allowlist):
            raise StoreError(f"artifact {name!r} is not in the allowlist")
        normalised = name.replace("\\", "/")
        if normalised.startswith("/") or ".." in normalised.split("/") or not _SAFE_ARTIFACT.match(normalised):
            raise StoreError(f"unsafe artifact name: {name!r}")
        root = self.run_dir(run_id).resolve()
        target = (root / normalised).resolve()
        if not str(target).startswith(str(root) + os.sep):
            raise StoreError(f"artifact escapes the run directory: {name!r}")
        return target

    # -- lifecycle -----------------------------------------------------
    def create_run(self, run_id: str, *, project_id: str = "demo", snapshot_id: str = "demo",
                   fixture_id: str = "demo-slice-300") -> Path:
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True, exist_ok=True)
        status_path = directory / "status.json"
        if not status_path.exists():
            self._atomic_write(status_path, {
                "run_id": run_id,
                "project_id": project_id,
                "snapshot_id": snapshot_id,
                "fixture_id": fixture_id,
                "status": "queued",
                "stage": "queued",
                "progress": {"stage": "queued", "files_done": 0, "files_total": 0, "percent": 0.0},
                "created_at": _utc_now(),
            })
        return directory

    def delete_run(self, run_id: str) -> None:
        directory = self.run_dir(run_id)
        if directory.exists():
            shutil.rmtree(directory)

    def list_runs(self) -> list[str]:
        return sorted(p.name for p in self.runs_dir.iterdir() if p.is_dir())

    # -- generic artifacts --------------------------------------------
    def _atomic_write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        if isinstance(data, str):
            text = data
        else:
            text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        with temp.open("w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        temp.replace(path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            os.fsync(dir_fd)
            os.close(dir_fd)
        except OSError:
            pass

    def write_artifact(self, run_id: str, name: str, data: Any) -> Path:
        target = self._artifact_path(run_id, name)
        self._atomic_write(target, data)
        return target

    def read_artifact(self, run_id: str, name: str, *, allowlist: Iterable[str] | None = None) -> Any:
        target = self._artifact_path(run_id, name, allowlist=allowlist)
        if not target.is_file():
            raise StoreError(f"artifact not found: {name!r}")
        text = target.read_text(encoding="utf-8")
        if target.suffix.lower() in {".json"}:
            return json.loads(text)
        if target.suffix.lower() in {".jsonl"}:
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        return text

    def exists(self, run_id: str, name: str) -> bool:
        try:
            return self._artifact_path(run_id, name).is_file()
        except StoreError:
            return False

    # -- run status ----------------------------------------------------
    def update_status(self, run_id: str, *, status: str, stage: str, percent: float,
                      files_done: int | None = None, files_total: int | None = None,
                      error: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self.run_dir(run_id) / "status.json"
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"run_id": run_id}
        payload["status"] = status
        payload["stage"] = stage
        payload.setdefault("progress", {})
        payload["progress"]["stage"] = stage
        payload["progress"]["percent"] = max(0.0, min(100.0, float(percent)))
        if files_done is not None:
            payload["progress"]["files_done"] = files_done
        if files_total is not None:
            payload["progress"]["files_total"] = files_total
        if status in {"succeeded", "failed", "cancelled"}:
            payload["finished_at"] = _utc_now()
        if error is not None:
            payload["error"] = error
        self._atomic_write(path, payload)
        return payload

    def read_status(self, run_id: str) -> dict[str, Any]:
        path = self.run_dir(run_id) / "status.json"
        if not path.exists():
            raise StoreError(f"run not found: {run_id!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    # -- audit ---------------------------------------------------------
    def read_audit(self, run_id: str) -> list[dict[str, Any]]:
        path = self.run_dir(run_id) / "audit.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def append_audit(self, run_id: str, *, action: str, object_type: str, object_id: str,
                     actor: str = "system", before_hash: str | None = None,
                     after_hash: str | None = None) -> dict[str, Any]:
        events = self.read_audit(run_id)
        prev_hash = events[-1]["hash"] if events else "GENESIS"
        event = {
            "schema_version": "1.0",
            "event_id": f"AE-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "seq": len(events),
            "ts": _utc_now(),
            "actor": actor,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "prev_hash": prev_hash,
        }
        event["hash"] = _hash_payload(event)
        path = self.run_dir(run_id) / "audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return event

    def verify_audit(self, run_id: str) -> bool:
        events = self.read_audit(run_id)
        prev = "GENESIS"
        for index, event in enumerate(events):
            if event.get("seq") != index:
                return False
            if event.get("prev_hash") != prev:
                return False
            observed = event.get("hash")
            payload = {k: v for k, v in event.items() if k != "hash"}
            if _hash_payload(payload) != observed:
                return False
            prev = observed
        return True

    # -- decisions -----------------------------------------------------
    def record_decision(self, run_id: str, *, object_type: str, object_id: str,
                        action: str, actor: str, reason: str,
                        before_hash: str | None = None, after_hash: str | None = None) -> dict[str, Any]:
        decisions_path = self.run_dir(run_id) / "decisions.json"
        payload = {"decisions": []}
        if decisions_path.exists():
            payload = json.loads(decisions_path.read_text(encoding="utf-8"))
        decision = {
            "schema_version": "1.0",
            "decision_id": f"D-{uuid.uuid4().hex[:12]}",
            "object_type": object_type,
            "object_id": object_id,
            "action": action,
            "actor": actor,
            "reason": reason,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "created_at": _utc_now(),
        }
        payload["decisions"].append(decision)
        self._atomic_write(decisions_path, payload)
        self.append_audit(
            run_id,
            action=f"{object_type}.{action}",
            object_type=object_type,
            object_id=object_id,
            actor=actor,
            before_hash=before_hash,
            after_hash=after_hash,
        )
        return decision
