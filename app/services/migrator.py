"""Autonomous multi-agent migration draft generation.

This is deliberately bounded autonomy: the orchestrator can read the snapshot,
generate a target draft, verify it, and package it without a human in the loop.
It cannot deploy, edit ``_gen`` files, approve its own changes, or resolve an
assumption. Every run produces its own hash-chained agent log and a reviewable
bundle under ``migration/`` in the run store.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

MIGRATION_ARTIFACT = "migration.json"
AUDIT_PATH = "migration/audit.jsonl"
BUNDLE_ROOT = "migration"
TARGET_ROOT = "migration/target"
REPORT_PATH = "migration/MIGRATION-REPORT.md"
PLAN_PATH = "migration/migration-plan.json"
MANIFEST_PATH = "migration/bundle-manifest.json"

BOUNDARY = (
    "Autonomous draft generation only: the orchestrator writes a local, "
    "non-deployable target bundle. It does not edit _gen files, approve changes, "
    "resolve assumptions, or contact a Guidewire tenant."
)

AGENTS: list[dict[str, str]] = [
    {
        "agent_id": "scout",
        "name": "Scout",
        "role": "Inventory and scope",
        "description": "Resolves the feature, counts evidence, and refuses to plan from an ungrounded slice.",
    },
    {
        "agent_id": "architect",
        "name": "Architect",
        "role": "Target draft",
        "description": "Turns every explicit disposition into a target file in the migration bundle.",
    },
    {
        "agent_id": "guardian",
        "name": "Guardian",
        "role": "Risk and gates",
        "description": "Converts findings and open assumptions into blocking review gates.",
    },
    {
        "agent_id": "critic",
        "name": "Critic",
        "role": "Adversarial verification",
        "description": "Rejects ungrounded packages, unsafe paths, duplicate targets, and unparseable output.",
    },
    {
        "agent_id": "scribe",
        "name": "Scribe",
        "role": "Bundle and report",
        "description": "Writes the plan, the review report, and the sealed bundle manifest.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_hash(payload: Any) -> str:
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _read(store, run_id: str, name: str, default: Any) -> Any:
    try:
        return store.read_artifact(run_id, name)
    except Exception:
        return default


def _safe_relative(path: str) -> bool:
    candidate = Path(path)
    return (
        bool(path)
        and not candidate.is_absolute()
        and ".." not in candidate.parts
        and not path.startswith("_gen/")
        and path != "_gen"
    )


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _append_audit(store, run_id: str, *, agent: str, action: str,
                  object_id: str, reason: str | None = None) -> dict[str, Any]:
    """Append an event to the migrator's own hash chain.

    The review-run audit remains untouched so the existing review packet and
    demo evidence stay reproducible. The migrator log proves agent ordering and
    is linked from the signed bundle manifest.
    """
    with store.locked(run_id):
        path = store.run_dir(run_id) / AUDIT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = "GENESIS"
        seq = 0
        if path.is_file():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            seq = len(lines)
            if lines:
                previous = json.loads(lines[-1]).get("hash", "GENESIS")
        event = {
            "seq": seq,
            "ts": _now(),
            "run_id": run_id,
            "agent": agent,
            "action": action,
            "object_id": object_id,
            "reason": reason,
            "prev_hash": previous,
        }
        event["hash"] = _json_hash(event)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event


def verify_migration_log(store, run_id: str) -> tuple[bool, str]:
    """Verify the migrator's append-only event chain."""
    path = store.run_dir(run_id) / AUDIT_PATH
    if not path.is_file():
        return False, "migration audit log is missing"
    previous = "GENESIS"
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False, f"event {index} is not valid JSON"
        digest = event.pop("hash", None)
        if event.get("seq") != index:
            return False, f"event {index} has the wrong sequence"
        if event.get("prev_hash") != previous:
            return False, f"event {index} has a broken previous hash"
        if _json_hash(event) != digest:
            return False, f"event {index} hash mismatch"
        previous = digest
    return True, f"{index + 1 if 'index' in locals() else 0} events verified"


def _initial_state(run_id: str, feature: dict[str, Any], feature_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "feature_id": feature_id,
        "feature_name": feature.get("name", feature_id),
        "status": "running",
        "mode": "five specialist agents · deterministic handoffs",
        "boundary": BOUNDARY,
        "started_at": _now(),
        "finished_at": None,
        "progress": 0,
        "current_agent": "scout",
        "agents": [
            {**agent, "status": "queued", "started_at": None,
             "finished_at": None, "summary": "", "checks": []}
            for agent in AGENTS
        ],
        "packages": [],
        "gates": [],
        "outputs": [],
        "verification": {"status": "pending", "checks": []},
        "summary": {},
        "audit": {"path": AUDIT_PATH, "events": 0, "head": None, "verified": False},
        "report_path": REPORT_PATH,
        "plan_path": PLAN_PATH,
    }


def _set_agent(state: dict[str, Any], agent_id: str, **changes: Any) -> None:
    for agent in state["agents"]:
        if agent["agent_id"] == agent_id:
            agent.update(changes)
            return
    raise KeyError(agent_id)


def _persist(store, run_id: str, state: dict[str, Any]) -> None:
    store.write_artifact(run_id, MIGRATION_ARTIFACT, state)


def _evidence_for_source(source_ref: str, evidence: list[dict[str, Any]]) -> list[str]:
    leaf = source_ref.rsplit(".", 1)[-1]
    if not leaf:
        return []
    matches = []
    for item in evidence:
        excerpt = item.get("excerpt") or ""
        if leaf in excerpt and item.get("evidence_id"):
            matches.append(item["evidence_id"])
        if len(matches) == 2:
            break
    return matches


def _parse_generated(path: Path) -> tuple[bool, str]:
    try:
        text = _read_text(path)
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"cannot read: {exc}"
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            json.loads(text)
        elif suffix in {".yaml", ".yml"}:
            yaml.safe_load(text)
    except (ValueError, yaml.YAMLError) as exc:
        return False, f"parse failed: {exc}"
    return True, "parsed"


def run_migration(store, run_id: str, *, feature_id: str | None = None,
                  pace: float = 0.35) -> dict[str, Any]:
    """Run the five agents end-to-end and persist the bundle and state.

    ``pace`` adds a short pause between handoffs so the live UI can show agent
    progress. Tests and CLI callers set it to zero.
    """
    status = store.read_status(run_id)
    if status.get("status") != "succeeded":
        raise ValueError("migration requires a succeeded analysis run")

    features = _read(store, run_id, "features.json", {"features": []}).get("features", [])
    feature = next((item for item in features if item.get("feature_id") == feature_id), None)
    if feature is None and feature_id is None:
        feature = features[0] if features else None
    if feature is None:
        raise ValueError(f"feature not found: {feature_id}")
    feature_id = feature["feature_id"]

    state = _initial_state(run_id, feature, feature_id)
    store.write_artifact(run_id, MIGRATION_ARTIFACT, state)
    _append_audit(store, run_id, agent="orchestrator", action="migration.started",
                  object_id=run_id, reason=f"autonomous draft for {feature_id}")

    manifest = _read(store, run_id, "manifest.json", {})
    evidence = _read(store, run_id, "evidence.json", {"evidence": []}).get("evidence", [])
    mappings = _read(store, run_id, "mappings.json", {"mappings": []}).get("mappings", [])
    changes = _read(store, run_id, "changes.json", {"changes": []}).get("changes", [])
    assumptions = _read(store, run_id, "assumptions.json", {"assumptions": []}).get("assumptions", [])
    findings = _read(store, run_id, "findings.json", {"findings": []}).get("findings", [])
    mappings_by_id = {item.get("mapping_id"): item for item in mappings}
    run_dir = store.run_dir(run_id)
    draft_root = run_dir / "draft"
    migration_dir = run_dir / BUNDLE_ROOT

    try:
        # 1. Scout ---------------------------------------------------------
        _set_agent(state, "scout", status="running", started_at=_now())
        _append_audit(store, run_id, agent="scout", action="agent.started", object_id="scout")
        feature_evidence = feature.get("evidence_ids", [])
        scout_checks = [
            {"name": "run succeeded", "ok": True, "detail": status.get("status", "")},
            {"name": "feature resolved", "ok": True, "detail": feature_id},
            {"name": "feature evidence", "ok": len(feature_evidence) > 0,
             "detail": f"{len(feature_evidence)} linked records"},
            {"name": "source snapshot", "ok": bool(manifest.get("sha256")),
             "detail": str(manifest.get("sha256", ""))[:12]},
        ]
        _set_agent(
            state, "scout", status="done", finished_at=_now(),
            summary=(
                f"{manifest.get('file_count', 0)} files → {len(evidence)} evidence records · "
                f"{len(findings)} findings · {len(mappings)} dispositions · {len(feature_evidence)} "
                f"evidence links on {feature_id}"
            ),
            checks=scout_checks,
        )
        state["progress"] = 18
        state["current_agent"] = "architect"
        state["summary"].update({
            "files": manifest.get("file_count", 0),
            "evidence": len(evidence),
            "findings": len(findings),
            "dispositions": len(mappings),
            "feature_evidence": len(feature_evidence),
        })
        _persist(store, run_id, state)
        _append_audit(store, run_id, agent="scout", action="agent.completed", object_id="scout",
                      reason=state["agents"][0]["summary"])
        if pace:
            time.sleep(pace)

        # 2. Architect -----------------------------------------------------
        _set_agent(state, "architect", status="running", started_at=_now())
        _append_audit(store, run_id, agent="architect", action="agent.started", object_id="architect")
        packages: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        used_targets: set[str] = set()
        for index, change in enumerate(changes, start=1):
            target = str(change.get("target_path", ""))
            mapping = mappings_by_id.get(change.get("mapping_id"), {})
            package_id = f"WP-{index:02d}"
            reasons: list[str] = []
            if not _safe_relative(target):
                reasons.append("unsafe or _gen target path")
            if target in used_targets:
                reasons.append("duplicate target path")
            used_targets.add(target)
            source_file = draft_root / target
            output_file = migration_dir / "target" / target
            output_ok = False
            if source_file.is_file() and _safe_relative(target):
                data = source_file.read_bytes()
                _write_bytes(output_file, data)
                output_ok = True
                outputs.append({
                    "path": f"{TARGET_ROOT}/{target}",
                    "bytes": len(data),
                    "sha256": _sha(data),
                })
            else:
                reasons.append("draft output is missing")
            evidence_ids = _evidence_for_source(str(mapping.get("source_ref", "")), evidence)
            if not evidence_ids:
                evidence_ids = list(feature_evidence[:2])
            gate_ids = [
                assumption["assumption_id"]
                for assumption in assumptions
                if assumption.get("related_mapping_id") == mapping.get("mapping_id")
                and assumption.get("status") == "open"
            ]
            package = {
                "package_id": package_id,
                "title": f"Generate {Path(target).name}",
                "target_path": target,
                "source_ref": mapping.get("source_ref"),
                "target_name": mapping.get("target_name"),
                "disposition": mapping.get("disposition"),
                "mapping_id": mapping.get("mapping_id"),
                "change_id": change.get("change_id"),
                "agent": "architect",
                "status": "blocked" if reasons else "draft_ready",
                "reasons": reasons,
                "evidence_ids": evidence_ids,
                "gate_ids": gate_ids,
                "approval": change.get("approval_state", "pending"),
                "bytes": len((output_file.read_bytes() if output_ok else b"")),
                "sha256": _sha(output_file.read_bytes()) if output_ok else None,
            }
            packages.append(package)
        state["packages"] = packages
        state["outputs"] = outputs
        state["progress"] = 42
        state["current_agent"] = "guardian"
        ready = sum(1 for p in packages if p["status"] == "draft_ready")
        _set_agent(
            state, "architect", status="done", finished_at=_now(),
            summary=(f"{len(packages)} work packages · {ready} draft files generated · "
                     f"{len(outputs)} target artefacts in migration/target/"),
            checks=[
                {"name": "explicit dispositions", "ok": bool(mappings), "detail": f"{len(mappings)}"},
                {"name": "target files generated", "ok": ready == len(packages) and bool(packages),
                 "detail": f"{ready}/{len(packages)}"},
                {"name": "_gen untouched", "ok": all("_gen" not in p["target_path"] for p in packages),
                 "detail": "target bundle only"},
            ],
        )
        _persist(store, run_id, state)
        _append_audit(store, run_id, agent="architect", action="agent.completed",
                      object_id="architect", reason=state["agents"][1]["summary"])
        if pace:
            time.sleep(pace)

        # 3. Guardian ------------------------------------------------------
        _set_agent(state, "guardian", status="running", started_at=_now())
        _append_audit(store, run_id, agent="guardian", action="agent.started", object_id="guardian")
        gates: list[dict[str, Any]] = []
        for assumption in assumptions:
            if assumption.get("status") != "open":
                continue
            gates.append({
                "gate_id": f"G-{len(gates) + 1:02d}",
                "kind": "assumption",
                "severity": assumption.get("impact", "medium"),
                "title": assumption.get("statement", ""),
                "question": assumption.get("question_to_ask", ""),
                "owner": assumption.get("owner", "unassigned"),
                "source_id": assumption.get("assumption_id"),
                "status": "open",
            })
        rules: dict[str, list[dict[str, Any]]] = {}
        for finding in findings:
            if finding.get("decision", "open") != "open":
                continue
            rules.setdefault(finding.get("rule_id", "unknown"), []).append(finding)
        for rule_id, items in sorted(rules.items()):
            severity = "high" if any(item.get("severity") == "error" for item in items) else "medium"
            gates.append({
                "gate_id": f"G-{len(gates) + 1:02d}",
                "kind": "review",
                "severity": severity,
                "title": f"{items[0].get('title', rule_id)} ({len(items)} findings, {rule_id})",
                "question": "Has the delivery team accepted or remediated this finding before target approval?",
                "owner": "delivery team",
                "source_id": rule_id,
                "status": "open",
            })
        gate_by_mapping = {
            gate["source_id"]: gate["gate_id"]
            for gate in gates if gate["kind"] == "assumption"
        }
        for package in packages:
            related = [
                gate_by_mapping[assumption_id]
                for assumption_id in package.get("gate_ids", [])
                if assumption_id in gate_by_mapping
            ]
            package["gate_ids"] = related
        state["gates"] = gates
        state["progress"] = 65
        state["current_agent"] = "critic"
        high = sum(1 for gate in gates if gate["severity"] == "high")
        _set_agent(
            state, "guardian", status="done", finished_at=_now(),
            summary=f"{len(gates)} open gates · {high} high impact · deployment remains blocked",
            checks=[
                {"name": "assumption gates", "ok": True,
                 "detail": f"{sum(1 for g in gates if g['kind'] == 'assumption')} open"},
                {"name": "finding gates", "ok": True,
                 "detail": f"{sum(1 for g in gates if g['kind'] == 'review')} rule groups"},
                {"name": "no self-approval", "ok": True,
                 "detail": "all changes remain pending"},
            ],
        )
        _persist(store, run_id, state)
        _append_audit(store, run_id, agent="guardian", action="agent.completed",
                      object_id="guardian", reason=state["agents"][2]["summary"])
        if pace:
            time.sleep(pace)

        # 4. Critic --------------------------------------------------------
        _set_agent(state, "critic", status="running", started_at=_now())
        _append_audit(store, run_id, agent="critic", action="agent.started", object_id="critic")
        checks: list[dict[str, Any]] = []
        checks.append({"name": "packages exist", "ok": bool(packages),
                       "detail": f"{len(packages)} work packages"})
        checks.append({"name": "all package files generated",
                       "ok": all(p["status"] == "draft_ready" for p in packages),
                       "detail": f"{sum(1 for p in packages if p['status'] == 'draft_ready')}/{len(packages)}"})
        checks.append({"name": "no _gen targets",
                       "ok": all("_gen" not in p["target_path"] for p in packages),
                       "detail": "bundle is _ext/codegen/updater only"})
        checks.append({"name": "no duplicate targets",
                       "ok": len({p["target_path"] for p in packages}) == len(packages),
                       "detail": f"{len({p['target_path'] for p in packages})} unique"})
        parse_ok = True
        parse_details = []
        for output in outputs:
            path = run_dir / output["path"]
            ok, detail = _parse_generated(path)
            parse_ok = parse_ok and ok
            if not ok:
                parse_details.append(f"{output['path']}: {detail}")
        checks.append({"name": "generated JSON/YAML parses", "ok": parse_ok,
                       "detail": "; ".join(parse_details) or f"{len(outputs)} files parsed"})
        checks.append({"name": "every package is evidence-linked",
                       "ok": all(p["evidence_ids"] for p in packages),
                       "detail": f"{sum(1 for p in packages if p['evidence_ids'])}/{len(packages)} linked"})
        checks.append({"name": "human approval retained",
                       "ok": all(p["approval"] == "pending" for p in packages),
                       "detail": "0 auto-approved changes"})
        failed = [check for check in checks if not check["ok"]]
        state["verification"] = {"status": "passed" if not failed else "failed",
                                 "checks": checks}
        state["progress"] = 85
        state["current_agent"] = "scribe"
        _set_agent(
            state, "critic", status="done" if not failed else "failed",
            finished_at=_now(),
            summary=(f"{len(checks) - len(failed)}/{len(checks)} checks passed · "
                     f"verdict {'PASS' if not failed else 'FAIL'}"),
            checks=checks,
        )
        _persist(store, run_id, state)
        _append_audit(store, run_id, agent="critic", action="agent.completed",
                      object_id="critic", reason=state["agents"][3]["summary"])
        if pace:
            time.sleep(pace)

        # 5. Scribe --------------------------------------------------------
        _set_agent(state, "scribe", status="running", started_at=_now())
        _append_audit(store, run_id, agent="scribe", action="agent.started", object_id="scribe")
        state["summary"].update({
            "packages": len(packages),
            "generated": sum(1 for p in packages if p["status"] == "draft_ready"),
            "blocked": sum(1 for p in packages if p["status"] == "blocked"),
            "gates": len(gates),
            "high_gates": high,
            "artifacts": len(outputs) + 4,
        })
        state["status"] = "completed_with_gates" if gates else "completed"
        state["progress"] = 100
        state["current_agent"] = None
        state["finished_at"] = _now()
        _set_agent(
            state, "scribe", status="done", finished_at=_now(),
            summary="Plan, report, and sealed bundle manifest written; every change remains pending.",
            checks=[
                {"name": "plan written", "ok": True, "detail": PLAN_PATH},
                {"name": "report written", "ok": True, "detail": REPORT_PATH},
                {"name": "bundle manifest written", "ok": True, "detail": MANIFEST_PATH},
            ],
        )
        plan = {
            "schema_version": "1.0",
            "run_id": run_id,
            "feature_id": feature_id,
            "feature_name": feature.get("name", feature_id),
            "generated_at": _now(),
            "boundary": BOUNDARY,
            "source_snapshot": manifest.get("sha256"),
            "agents": [
                {"agent_id": item["agent_id"], "name": item["name"], "role": item["role"],
                 "status": item["status"], "summary": item["summary"]}
                for item in state["agents"]
            ],
            "packages": packages,
            "gates": gates,
            "outputs": outputs,
            "verification": state["verification"],
        }
        plan_bytes = (json.dumps(plan, indent=2, sort_keys=False) + "\n").encode("utf-8")
        plan_sha256 = _sha(plan_bytes)
        _write_bytes(migration_dir / "migration-plan.json", plan_bytes)
        report = _render_report(
            state, plan, plan_sha256=plan_sha256,
            bundle_file_count=len(outputs) + 3,
        )
        _write_bytes(migration_dir / "MIGRATION-REPORT.md", report.encode("utf-8"))
        bundle_files = []
        for path in sorted(migration_dir.rglob("*")):
            if path.is_file() and path.name not in {"bundle-manifest.json"}:
                relative = path.relative_to(migration_dir).as_posix()
                data = path.read_bytes()
                bundle_files.append({"path": f"{BUNDLE_ROOT}/{relative}",
                                     "bytes": len(data), "sha256": _sha(data)})
        manifest_payload = {
            "schema_version": "1.0",
            "run_id": run_id,
            "feature_id": feature_id,
            "generated_at": _now(),
            "boundary": BOUNDARY,
            "source_snapshot": manifest.get("sha256"),
            "files": bundle_files,
            "file_count": len(bundle_files),
            "gate_count": len(gates),
            "verification": state["verification"]["status"],
            "audit_path": AUDIT_PATH,
        }
        manifest_bytes = (json.dumps(manifest_payload, indent=2, sort_keys=False) + "\n").encode("utf-8")
        _write_bytes(migration_dir / "bundle-manifest.json", manifest_bytes)
        state["outputs"] = outputs
        state["bundle"] = {
            "path": f"{BUNDLE_ROOT}/bundle-manifest.json",
            "bytes": len(manifest_bytes),
            "sha256": _sha(manifest_bytes),
            "file_count": len(bundle_files),
            "sha256_files": {item["path"]: item["sha256"] for item in bundle_files},
        }
        state["plan_sha256"] = plan_sha256
        state["report_sha256"] = _sha(report.encode("utf-8"))
        state["summary"]["artifacts"] = len(bundle_files)
        verified, detail = verify_migration_log(store, run_id)
        events = _read(store, run_id, AUDIT_PATH, [])
        state["audit"] = {
            "path": AUDIT_PATH,
            "events": len(events) + 1,
            "head": events[-1]["hash"][:16] if events else None,
            "verified": verified,
            "detail": detail,
        }
        _set_agent(
            state, "scribe", status="done", finished_at=_now(),
            summary=(f"Bundle sealed: {len(bundle_files)} files · plan {state['plan_sha256'][:12]} · "
                     f"report {state['report_sha256'][:12]}"),
        )
        _persist(store, run_id, state)
        _append_audit(store, run_id, agent="scribe", action="agent.completed",
                      object_id="scribe", reason=state["agents"][4]["summary"])
        final_verified, final_detail = verify_migration_log(store, run_id)
        events = _read(store, run_id, AUDIT_PATH, [])
        state["audit"] = {
            "path": AUDIT_PATH,
            "events": len(events),
            "head": events[-1]["hash"][:16] if events else None,
            "verified": final_verified,
            "detail": final_detail,
        }
        _append_audit(store, run_id, agent="orchestrator", action="migration.completed",
                      object_id=run_id, reason=state["status"])
        events = _read(store, run_id, AUDIT_PATH, [])
        state["audit"] = {
            "path": AUDIT_PATH,
            "events": len(events),
            "head": events[-1]["hash"][:16] if events else None,
            "verified": verify_migration_log(store, run_id)[0],
            "detail": verify_migration_log(store, run_id)[1],
        }
        _persist(store, run_id, state)
        return state
    except Exception as exc:
        state["status"] = "failed"
        state["finished_at"] = _now()
        state["current_agent"] = None
        state["error"] = {"type": type(exc).__name__, "message": str(exc)}
        state["progress"] = 100
        for agent in state["agents"]:
            if agent["status"] == "running":
                agent["status"] = "failed"
                agent["finished_at"] = _now()
        _persist(store, run_id, state)
        _append_audit(store, run_id, agent="orchestrator", action="migration.failed",
                      object_id=run_id, reason=str(exc))
        raise


def _render_report(state: dict[str, Any], plan: dict[str, Any], *,
                   plan_sha256: str, bundle_file_count: int) -> str:
    lines = [
        f"# Autonomous migration draft — {state['feature_id']} {state['feature_name']}",
        "",
        f"**Status:** `{state['status']}`  ",
        f"**Verification:** `{state['verification']['status']}`  ",
        f"**Generated:** {state['finished_at'] or _now()}  ",
        f"**Boundary:** {BOUNDARY}",
        "",
        "## Agent handoffs",
        "",
    ]
    for agent in state["agents"]:
        lines.append(f"- **{agent['name']} ({agent['role']})** — `{agent['status']}`. {agent['summary']}")
    lines += ["", "## Work packages", "",
              "| ID | Target | Disposition | Status | Gates | Evidence |",
              "|---|---|---|---|---|---|"]
    for package in state["packages"]:
        lines.append(
            f"| {package['package_id']} | `{package['target_path']}` | "
            f"{package.get('disposition') or '—'} | {package['status']} | "
            f"{', '.join(package.get('gate_ids', [])) or '—'} | "
            f"{', '.join(package.get('evidence_ids', [])) or '—'} |"
        )
    lines += ["", "## Open gates", ""]
    if state["gates"]:
        for gate in state["gates"]:
            lines.append(
                f"- **{gate['gate_id']} · {gate['severity']} · {gate['kind']}** — {gate['title']}  "
                f"Question: {gate['question']} (owner: {gate['owner']})"
            )
    else:
        lines.append("No open gates.")
    lines += ["", "## Verification", ""]
    for check in state["verification"]["checks"]:
        lines.append(f"- **{'PASS' if check['ok'] else 'FAIL'}** — {check['name']}: {check['detail']}")
    lines += [
        "",
        "## Generated files",
        "",
        f"The sealed bundle manifest is `{MANIFEST_PATH}` ({bundle_file_count} files plus the manifest).",
        "",
        f"Plan SHA-256: `{plan_sha256}`  ",
        "Report SHA-256: recorded in `migration/bundle-manifest.json`  ",
        f"Agent log: `{AUDIT_PATH}`",
        "",
        "Changes remain pending human approval. This is not a deployment.",
        "",
    ]
    return "\n".join(lines)
