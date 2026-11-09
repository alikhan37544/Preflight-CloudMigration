"""JSON run store with atomic writes and a hash-chained audit log.

Concurrency model
-----------------
Every run has two locks: a process-local :class:`threading.RLock` and an
inter-process ``fcntl.flock`` on ``<base>/.locks/<run_id>.lock``.  Use
:meth:`RunStore.locked` for any read-modify-write sequence.  It combines both
locks and is re-entrant within a thread, so store helpers such as
:meth:`RunStore.record_decision` and :meth:`RunStore.append_audit` can
re-acquire it without deadlocking.  Mutating helpers take the lock themselves;
a caller that needs several of them to commit together (artifact write +
audit + decision) must wrap the whole sequence in ``with store.locked(run_id)``.

The flock serialises independent processes sharing one data directory.  It is
still advisory: callers outside this store (or filesystem copies that bypass
the lock file) are not protected.  Lock files live outside ``runs/`` so that
deleting a run cannot split a lock into two inodes.  Deleted run ids also leave
a tombstone under ``.deleted/``; late writers fail with ``StoreError`` instead
of resurrecting the directory.

Decision state machine
----------------------
Per object the review state is one of ``pending`` (findings: ``open``),
``accepted``, ``rejected``, ``deferred`` or ``edited``.  The API only applies a
mutation from the pending state.  Repeating the action that produced the
current terminal state is idempotent: it returns the existing object without
writing another decision or audit event.  A different action against a terminal
state is a conflict (HTTP 409).  Mapping rejection also creates exactly one
assumption (deduplicated by ``related_mapping_id``) in the same transaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import fcntl

_SAFE_RUN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SAFE_ARTIFACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
_CHECKPOINT_NAME = "audit.checkpoint.json"
_MAX_RUN_ID = 128


class StoreError(ValueError):
    """Raised for unsafe, missing, or corrupt store operations.

    ``code`` is stable enough for the HTTP layer to map corruption to
    ``CORRUPT_ARTIFACT`` (500) and invalid ids to a 400/404 response.
    """

    def __init__(self, message: str, *, code: str = "STORE_ERROR") -> None:
        super().__init__(message)
        self.code = code


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class RunStore:
    # Locks are shared between RunStore instances pointed at the same directory
    # so that two callers in one process cannot interleave a read-modify-write.
    _locks_guard = threading.Lock()
    _locks: dict[tuple[str, str], threading.RLock] = {}
    # Per-thread nesting depth for locked(). Re-entering the same run must not
    # open a second flock descriptor: a second flock in the same process would
    # block on the lock it already owns.
    _lock_depth = threading.local()
    _packet_cache_guard = threading.Lock()
    _packet_cache: dict[str, tuple] = {}
    _packet_cache_limit = 256

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.runs_dir = self.base_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def _lock_key(self, run_id: str) -> tuple[str, str]:
        return (str(self.runs_dir.resolve()), run_id)

    def _lock(self, run_id: str) -> threading.RLock:
        self.run_dir(run_id)  # validate before using the id as a lock key
        key = self._lock_key(run_id)
        with RunStore._locks_guard:
            lock = RunStore._locks.get(key)
            if lock is None:
                lock = threading.RLock()
                RunStore._locks[key] = lock
            return lock

    def _lock_path(self, run_id: str) -> Path:
        # Keep lock files outside runs/ so delete_run() cannot unlink the inode
        # that another process is currently blocking on.
        return self.base_dir / ".locks" / f"{run_id}.lock"

    def _tombstone_path(self, run_id: str) -> Path:
        return self.base_dir / ".deleted" / f"{run_id}.json"

    def _acquire_file_lock(self, run_id: str):
        handle = None
        try:
            path = self._lock_path(run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = path.open("a+", encoding="utf-8")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            return handle
        except OSError as exc:
            if handle is not None:
                handle.close()
            raise StoreError(
                f"cannot lock run {run_id!r}: {exc}", code="LOCK_ERROR"
            ) from exc

    @staticmethod
    def _release_file_lock(handle) -> None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    @contextmanager
    def locked(self, run_id: str) -> Iterator[None]:
        """Serialise a run-level transaction within and across processes.

        The context manager is re-entrant per thread.  Nested use (for example
        ``locked()`` -> ``record_decision()`` -> ``append_audit()``) increments
        a thread-local depth and never attempts a second flock.  Use it around
        the complete read -> validate -> mutate -> write -> audit -> decision
        sequence; do not hold it while doing slow work such as packet rendering.
        """
        self.run_dir(run_id)  # validate the id before creating lock paths
        lock = self._lock(run_id)
        key = self._lock_key(run_id)
        with lock:
            depth = getattr(RunStore._lock_depth, "depths", None)
            if depth is None:
                depth = {}
                RunStore._lock_depth.depths = depth
            current = depth.get(key, 0)
            file_lock = self._acquire_file_lock(run_id) if current == 0 else None
            depth[key] = current + 1
            try:
                yield
            finally:
                depth[key] = current
                if current == 0:
                    del depth[key]
                    if file_lock is not None:
                        self._release_file_lock(file_lock)

    def _ensure_not_deleted_locked(self, run_id: str) -> None:
        if self._tombstone_path(run_id).exists():
            raise StoreError(
                f"run {run_id!r} was deleted; refusing to recreate it",
                code="RUN_DELETED",
            )

    # -- paths ---------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        if (
            not isinstance(run_id, str)
            or len(run_id) > _MAX_RUN_ID
            or not _SAFE_RUN.match(run_id)
            or ".." in run_id
        ):
            raise StoreError(f"unsafe run id: {run_id!r}", code="INVALID_RUN_ID")
        return self.runs_dir / run_id

    def _artifact_path(self, run_id: str, name: str, allowlist: Iterable[str] | None = None) -> Path:
        if allowlist is not None and name not in set(allowlist):
            raise StoreError(f"artifact {name!r} is not in the allowlist", code="INVALID_ARTIFACT")
        normalised = name.replace("\\", "/")
        if normalised.startswith("/") or ".." in normalised.split("/") or not _SAFE_ARTIFACT.match(normalised):
            raise StoreError(f"unsafe artifact name: {name!r}", code="INVALID_ARTIFACT")
        root = self.run_dir(run_id).resolve()
        target = (root / normalised).resolve()
        if not str(target).startswith(str(root) + os.sep):
            raise StoreError(f"artifact escapes the run directory: {name!r}", code="INVALID_ARTIFACT")
        return target

    # -- lifecycle -----------------------------------------------------
    def create_run(self, run_id: str, *, project_id: str = "demo", snapshot_id: str = "demo",
                   fixture_id: str = "demo-slice-300") -> Path:
        directory = self.run_dir(run_id)
        with self.locked(run_id):
            # An explicit create with a reused id starts a new generation and
            # clears the tombstone left by a previous delete.
            self._tombstone_path(run_id).unlink(missing_ok=True)
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
        with self.locked(run_id):
            # Tombstone first: a worker that is still unwinding must fail its
            # next write rather than recreate the directory after rmtree.
            marker = self._tombstone_path(run_id)
            self._atomic_write(marker, {"run_id": run_id, "deleted_at": _utc_now()})
            self.clear_packet_cache(run_id)
            if directory.exists():
                try:
                    shutil.rmtree(directory)
                except OSError as exc:
                    raise StoreError(
                        f"cannot delete run {run_id!r}: {exc}", code="STORE_ERROR"
                    ) from exc

    def list_runs(self) -> list[str]:
        try:
            return sorted(p.name for p in self.runs_dir.iterdir() if p.is_dir())
        except OSError as exc:
            raise StoreError(f"cannot list runs: {exc}", code="STORE_ERROR") from exc

    # -- generic artifacts --------------------------------------------
    def _atomic_write(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            text = data
        else:
            text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        # A unique temp file in the destination directory prevents concurrent
        # writers from sharing (and corrupting) one fixed ".tmp" path.
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            temp.replace(path)
        except BaseException:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            os.fsync(dir_fd)
            os.close(dir_fd)
        except OSError:
            pass

    def _read_text(self, path: Path, label: str) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise StoreError(f"{label} not found", code="NOT_FOUND") from exc
        except UnicodeDecodeError as exc:
            raise StoreError(f"{label} is not valid UTF-8", code="UNREADABLE") from exc
        except OSError as exc:
            raise StoreError(f"cannot read {label}: {exc}", code="UNREADABLE") from exc

    @staticmethod
    def _parse_json(text: str, label: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise StoreError(
                f"{label} is corrupt or incomplete: {exc.msg}",
                code="CORRUPT_ARTIFACT",
            ) from exc

    def _read_json_file(self, path: Path, label: str) -> Any:
        return self._parse_json(self._read_text(path, label), label)

    def write_artifact(self, run_id: str, name: str, data: Any) -> Path:
        target = self._artifact_path(run_id, name)
        with self.locked(run_id):
            self._ensure_not_deleted_locked(run_id)
            self._atomic_write(target, data)
            self.clear_packet_cache(run_id)
        return target

    def read_artifact(self, run_id: str, name: str, *, allowlist: Iterable[str] | None = None) -> Any:
        target = self._artifact_path(run_id, name, allowlist=allowlist)
        with self.locked(run_id):
            if not target.is_file():
                raise StoreError(f"artifact not found: {name!r}", code="NOT_FOUND")
            text = self._read_text(target, f"artifact {name!r}")
        suffix = target.suffix.lower()
        if suffix == ".json":
            return self._parse_json(text, f"artifact {name!r}")
        if suffix == ".jsonl":
            items = []
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise StoreError(
                        f"artifact {name!r} is corrupt at line {line_number}: {exc.msg}",
                        code="CORRUPT_ARTIFACT",
                    ) from exc
            return items
        return text

    def exists(self, run_id: str, name: str) -> bool:
        try:
            return self._artifact_path(run_id, name).is_file()
        except StoreError:
            return False

    # -- packet refresh cache -----------------------------------------
    def _stat_token(self, path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _packet_audit_token_locked(self, run_id: str) -> tuple:
        """Cheap audit identity: checkpoint when valid, otherwise log stat."""
        audit_path = self.run_dir(run_id) / "audit.jsonl"
        try:
            checkpoint = self._read_checkpoint_locked(run_id)
        except StoreError:
            checkpoint = None
        if checkpoint is not None:
            count = checkpoint.get("count")
            head = checkpoint.get("head", "GENESIS")
            log_size = checkpoint.get("log_size")
            if (isinstance(count, int) and not isinstance(count, bool)
                    and isinstance(head, str)
                    and isinstance(log_size, int) and not isinstance(log_size, bool)):
                return ("checkpoint", count, head, log_size)
        return ("log", self._stat_token(audit_path))

    def packet_input_fingerprint(self, run_id: str,
                                 artifact_names: Iterable[str],
                                 extra_paths: Iterable[Path] = ()) -> tuple:
        """Fingerprint every input that can change packet content.

        Mtimes/sizes are intentional: hashing multi-megabyte artifacts on every
        page view would recreate the cost the cache exists to avoid. The audit
        token is the checkpoint head/count, so a decision always invalidates.
        """
        names = tuple(sorted(set(artifact_names)))
        with self.locked(run_id):
            artifacts = tuple(
                (name, self._stat_token(self._artifact_path(run_id, name)))
                for name in names
            )
            audit = self._packet_audit_token_locked(run_id)
        extras = tuple((str(path), self._stat_token(Path(path))) for path in extra_paths)
        return (audit, artifacts, extras)

    def _packet_key(self, run_id: str) -> tuple[str, str]:
        return (str(self.runs_dir.resolve()), run_id)

    def packet_cache_hit(self, run_id: str, fingerprint: tuple) -> bool:
        key = self._packet_key(run_id)
        with RunStore._packet_cache_guard:
            return RunStore._packet_cache.get(key) == fingerprint

    def store_packet_fingerprint(self, run_id: str, fingerprint: tuple) -> None:
        key = self._packet_key(run_id)
        with RunStore._packet_cache_guard:
            cache = RunStore._packet_cache
            cache[key] = fingerprint
            while len(cache) > RunStore._packet_cache_limit:
                cache.pop(next(iter(cache)))

    def clear_packet_cache(self, run_id: str | None = None) -> None:
        with RunStore._packet_cache_guard:
            if run_id is None:
                RunStore._packet_cache.clear()
                return
            RunStore._packet_cache.pop(self._packet_key(run_id), None)

    # -- run status ----------------------------------------------------
    def update_status(self, run_id: str, *, status: str, stage: str, percent: float,
                      files_done: int | None = None, files_total: int | None = None,
                      error: dict[str, Any] | None = None,
                      metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        path = self.run_dir(run_id) / "status.json"
        with self.locked(run_id):
            self._ensure_not_deleted_locked(run_id)
            if path.exists():
                payload = self._read_json_file(path, f"status for run {run_id!r}")
                if not isinstance(payload, dict):
                    raise StoreError(
                        f"status for run {run_id!r} is corrupt",
                        code="CORRUPT_ARTIFACT",
                    )
            else:
                payload = {"run_id": run_id}
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
            if metadata:
                payload.update(metadata)
            self._atomic_write(path, payload)
            return payload

    def read_status(self, run_id: str) -> dict[str, Any]:
        path = self.run_dir(run_id) / "status.json"
        with self.locked(run_id):
            if not path.exists():
                raise StoreError(f"run not found: {run_id!r}", code="NOT_FOUND")
            payload = self._read_json_file(path, f"status for run {run_id!r}")
        if not isinstance(payload, dict):
            raise StoreError(
                f"status for run {run_id!r} is corrupt", code="CORRUPT_ARTIFACT"
            )
        return payload

    # -- audit ---------------------------------------------------------
    def read_audit(self, run_id: str) -> list[dict[str, Any]]:
        with self.locked(run_id):
            return self._read_audit_locked(run_id)

    def _read_audit_locked(self, run_id: str) -> list[dict[str, Any]]:
        path = self.run_dir(run_id) / "audit.jsonl"
        if not path.exists():
            return []
        text = self._read_text(path, f"audit log for run {run_id!r}")
        events: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            event = self._parse_json(
                line, f"audit log for run {run_id!r} (line {line_number})"
            )
            if not isinstance(event, dict):
                raise StoreError(
                    f"audit log for run {run_id!r} is corrupt at line {line_number}",
                    code="CORRUPT_ARTIFACT",
                )
            events.append(event)
        return events

    def _checkpoint_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / _CHECKPOINT_NAME

    def _read_checkpoint_locked(self, run_id: str) -> dict[str, Any] | None:
        path = self._checkpoint_path(run_id)
        if not path.exists():
            return None
        payload = self._read_json_file(path, f"audit checkpoint for run {run_id!r}")
        if not isinstance(payload, dict):
            raise StoreError(f"audit checkpoint for run {run_id!r} is corrupt")
        return payload

    def _audit_state_locked(
        self, run_id: str
    ) -> tuple[bool, int, str | None]:
        audit_path = self.run_dir(run_id) / "audit.jsonl"
        checkpoint_path = self._checkpoint_path(run_id)
        existed = audit_path.exists()
        size = audit_path.stat().st_size if existed else 0
        checkpoint = (
            checkpoint_path.read_text(encoding="utf-8")
            if checkpoint_path.exists()
            else None
        )
        return existed, size, checkpoint

    def _restore_audit_locked(
        self, run_id: str, existed: bool, size: int, checkpoint: str | None
    ) -> None:
        """Best-effort rollback used when the paired write cannot complete."""
        try:
            audit_path = self.run_dir(run_id) / "audit.jsonl"
            checkpoint_path = self._checkpoint_path(run_id)
            if existed:
                with audit_path.open("r+b") as fh:
                    fh.truncate(size)
                    fh.flush()
                    os.fsync(fh.fileno())
            else:
                audit_path.unlink(missing_ok=True)
            if checkpoint is None:
                checkpoint_path.unlink(missing_ok=True)
            else:
                self._atomic_write(checkpoint_path, checkpoint)
        except Exception:
            # Never hide the original write failure with a rollback failure.
            pass

    def _audit_tail_locked(self, run_id: str) -> tuple[int, str, int]:
        """Return ``(count, head_hash, log_size)`` without scanning the log.

        The checkpoint is the fast path. It is rebuilt from the log when it is
        missing/corrupt (or predates the stored byte offset). A checkpoint that
        is present but disagrees with the log size is corruption: appending would
        otherwise let a truncated log continue from a stale head.
        """
        audit_path = self.run_dir(run_id) / "audit.jsonl"
        checkpoint_path = self._checkpoint_path(run_id)
        rebuild = False
        if checkpoint_path.exists():
            try:
                checkpoint = self._read_checkpoint_locked(run_id)
            except StoreError:
                checkpoint = None
                rebuild = True
            if checkpoint is None:
                rebuild = True
            else:
                count = checkpoint.get("count")
                head = checkpoint.get("head", "GENESIS")
                log_size = checkpoint.get("log_size")
                valid = (
                    isinstance(count, int) and not isinstance(count, bool)
                    and isinstance(head, str)
                    and (count > 0 or head == "GENESIS")
                )
                if not valid:
                    rebuild = True
                elif not isinstance(log_size, int) or isinstance(log_size, bool):
                    # Legacy checkpoint: one full read to learn the byte offset.
                    rebuild = True
                else:
                    try:
                        actual_size = audit_path.stat().st_size
                    except OSError:
                        actual_size = 0
                    if actual_size != log_size:
                        raise StoreError(
                            f"audit log for run {run_id!r} does not match its checkpoint",
                            code="CORRUPT_ARTIFACT",
                        )
                    return count, head, actual_size
        else:
            rebuild = True
        if not rebuild:
            return 0, "GENESIS", 0
        events = self._read_audit_locked(run_id)
        if events:
            head = events[-1].get("hash")
            if not isinstance(head, str):
                raise StoreError(
                    f"audit log for run {run_id!r} is corrupt: missing hash",
                    code="CORRUPT_ARTIFACT",
                )
        else:
            head = "GENESIS"
        try:
            size = audit_path.stat().st_size
        except OSError:
            size = 0
        return len(events), head, size

    def _append_audit_locked(
        self, run_id: str, *, action: str, object_type: str, object_id: str,
        actor: str = "system", before_hash: str | None = None,
        after_hash: str | None = None, reason: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_not_deleted_locked(run_id)
        count, prev_hash, _log_size = self._audit_tail_locked(run_id)
        event = {
            "schema_version": "1.0",
            "event_id": f"AE-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "seq": count,
            "ts": _utc_now(),
            "actor": actor,
            "action": action,
            "object_type": object_type,
            "object_id": object_id,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "prev_hash": prev_hash,
        }
        if reason is not None:
            event["reason"] = reason
        event["hash"] = _hash_payload(event)
        path = self.run_dir(run_id) / "audit.jsonl"
        checkpoint_path = self._checkpoint_path(run_id)
        state = self._audit_state_locked(run_id)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            log_size = path.stat().st_size
            self._atomic_write(checkpoint_path, {
                "schema_version": "1.0",
                "run_id": run_id,
                "count": count + 1,
                "head": event["hash"],
                "log_size": log_size,
                "updated_at": _utc_now(),
            })
        except BaseException:
            self._restore_audit_locked(run_id, *state)
            raise
        return event

    def append_audit(self, run_id: str, *, action: str, object_type: str, object_id: str,
                     actor: str = "system", before_hash: str | None = None,
                     after_hash: str | None = None,
                     reason: str | None = None) -> dict[str, Any]:
        with self.locked(run_id):
            return self._append_audit_locked(
                run_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                actor=actor,
                before_hash=before_hash,
                after_hash=after_hash,
                reason=reason,
            )

    def verify_audit(self, run_id: str) -> bool:
        with self.locked(run_id):
            try:
                events = self._read_audit_locked(run_id)
            except StoreError:
                return False

            prev = "GENESIS"
            for index, event in enumerate(events):
                if event.get("run_id") != run_id:
                    return False
                if event.get("seq") != index:
                    return False
                if event.get("prev_hash") != prev:
                    return False
                observed = event.get("hash")
                payload = {k: v for k, v in event.items() if k != "hash"}
                if not isinstance(observed, str) or _hash_payload(payload) != observed:
                    return False
                prev = observed

            try:
                checkpoint = self._read_checkpoint_locked(run_id)
            except StoreError:
                return False
            if checkpoint is not None:
                if checkpoint.get("run_id") not in (None, run_id):
                    return False
                count = checkpoint.get("count")
                if not isinstance(count, int) or isinstance(count, bool):
                    return False
                if count != len(events):
                    return False
                expected_head = events[-1]["hash"] if events else "GENESIS"
                if checkpoint.get("head", "GENESIS") != expected_head:
                    return False
                log_size = checkpoint.get("log_size")
                if log_size is not None:
                    if not isinstance(log_size, int) or isinstance(log_size, bool):
                        return False
                    audit_path = self.run_dir(run_id) / "audit.jsonl"
                    try:
                        actual_size = audit_path.stat().st_size
                    except OSError:
                        actual_size = 0
                    if actual_size != log_size:
                        return False
            return True

    # -- decisions -----------------------------------------------------
    def record_decision(self, run_id: str, *, object_type: str, object_id: str,
                        action: str, actor: str, reason: str,
                        before_hash: str | None = None, after_hash: str | None = None) -> dict[str, Any]:
        """Append a decision and its audit event as one locked unit.

        The caller is responsible for enforcing the state machine before
        calling this method.  Expected transitions are ``pending`` ->
        ``accepted``/``rejected``/``deferred``/``edited``; retrying the action
        that produced the current terminal state must not call this method
        again.  Calling it re-entrantly from :meth:`locked` is safe.
        """
        with self.locked(run_id):
            self._ensure_not_deleted_locked(run_id)
            decisions_path = self.run_dir(run_id) / "decisions.json"
            payload = {"decisions": []}
            if decisions_path.exists():
                payload = self._read_json_file(
                    decisions_path, f"decisions for run {run_id!r}"
                )
                if not isinstance(payload, dict) or not isinstance(payload.get("decisions"), list):
                    raise StoreError(
                        f"decisions for run {run_id!r} is corrupt",
                        code="CORRUPT_ARTIFACT",
                    )
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
            audit_state = self._audit_state_locked(run_id)
            # Audit first: if this fails, the decision is never persisted.
            self.append_audit(
                run_id,
                action=f"{object_type}.{action}",
                object_type=object_type,
                object_id=object_id,
                actor=actor,
                before_hash=before_hash,
                after_hash=after_hash,
                reason=reason,
            )
            payload["decisions"].append(decision)
            try:
                self._atomic_write(decisions_path, payload)
            except BaseException:
                self._restore_audit_locked(run_id, *audit_state)
                raise
            return decision
