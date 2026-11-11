"""Resilience for mid-migration platform upgrades and unexpected inputs.

A migration assessment can be active for weeks. The target cloud release can
move underneath it. This module models that reality explicitly:

* an upgrade event names the old and new release and the rules it perturbs;
* every prior green signal is invalidated rather than silently reused;
* affected patches are revalidated against the new effective constraints;
* a resume plan records whether to re-run the Architect, roll back to the last
  checkpoint, or defer the upgrade.

It also wraps scanning so source changes, corrupt files, duplicate targets, and
analyzer failures become named, reviewable states instead of crashes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.codeanalyzer import ScanResult, _tree_hash, analyze_codebase

SCENARIOS: dict[str, dict[str, Any]] = {
    "GWCP-APD-NAMING-2027.04": {
        "scenario_id": "GWCP-APD-NAMING-2027.04",
        "label": "APD import limit tightens from 24 to 20 characters",
        "from_version": "GWCP 2026.10",
        "to_version": "GWCP 2027.04",
        "severity": "high",
        "description": (
            "The target release shortens the APD product-template type-name import "
            "limit. Existing codegen overrides and generated endpoints must be "
            "regenerated before the migration can keep its green signal."
        ),
        "affected_rules": ["PF-CODE-APD-001"],
        "affected_paths": ["config/codegen/", "product/template/"],
        "effective": {"apd_name_limit": 20},
        "required_action": "Regenerate codegen nameOverride entries and endpoint drafts at 20 characters.",
        "owner": "APD / product model owner",
    },
    "GWCP-APP-EVENTS-V2-2027.04": {
        "scenario_id": "GWCP-APP-EVENTS-V2-2027.04",
        "label": "App Events envelope moves to schema v2",
        "from_version": "GWCP 2026.10",
        "to_version": "GWCP 2027.04",
        "severity": "high",
        "description": (
            "The App Events envelope adds required tenant and event identity fields. "
            "Generated publication drafts must be revalidated against the new contract."
        ),
        "affected_rules": ["PF-CODE-MSG-001"],
        "affected_paths": ["config/appevents/"],
        "effective": {"app_events_schema": "2.0"},
        "required_action": "Re-run the App Events contract check and add tenantId/eventId envelope fields.",
        "owner": "Integration owner",
    },
    "GWCP-GATEWAY-MTLS-2027.04": {
        "scenario_id": "GWCP-GATEWAY-MTLS-2027.04",
        "label": "Integration Gateway requires mTLS and scoped service auth",
        "from_version": "GWCP 2026.10",
        "to_version": "GWCP 2027.04",
        "severity": "medium",
        "description": (
            "Gateway routes require mutual TLS and a scoped service identity. "
            "Legacy gateway drafts that only name a service user are no longer sufficient."
        ),
        "affected_rules": ["PF-CODE-SRV-001", "PF-CODE-MSG-001"],
        "affected_paths": ["config/cloudapi/", "config/appevents/"],
        "effective": {"gateway_auth": "mtls+scoped-service"},
        "required_action": "Add mTLS and scoped service authorization to each route draft.",
        "owner": "Platform integration owner",
    },
    "GWCP-GOSU-API-REMOVAL-2027.04": {
        "scenario_id": "GWCP-GOSU-API-REMOVAL-2027.04",
        "label": "A deprecated Gosu API is removed from the target runtime",
        "from_version": "GWCP 2026.10",
        "to_version": "GWCP 2027.04",
        "severity": "high",
        "description": (
            "A deprecated runtime API used by an earlier refactor is removed. "
            "Every target draft that still references it must be regenerated or rolled back."
        ),
        "affected_rules": ["PF-CODE-API-001", "PF-CODE-API-002"],
        "affected_paths": ["gsrc/", "java/", "plugins/"],
        "effective": {"removed_runtime_apis": ["java.rmi", "javax.ejb", "gw.internal"]},
        "required_action": "Re-run the Architect on affected classes and replace the removed API.",
        "owner": "Application development owner",
    },
    "GWCP-CLOUD-API-VERSION-2027.04": {
        "scenario_id": "GWCP-CLOUD-API-VERSION-2027.04",
        "label": "Cloud API extension routes move to a new version prefix",
        "from_version": "GWCP 2026.10",
        "to_version": "GWCP 2027.04",
        "severity": "medium",
        "description": (
            "Cloud API extension routes must advertise the new version prefix. "
            "Legacy route drafts are revalidated but do not block the code-level green signal."
        ),
        "affected_rules": ["PF-CODE-SRV-001"],
        "affected_paths": ["config/cloudapi/"],
        "effective": {"cloud_api_version": "v2"},
        "required_action": "Regenerate the route draft with the v2 prefix and update consumers.",
        "owner": "API product owner",
    },
}

UNEXPECTED_SCENARIOS: dict[str, dict[str, Any]] = {
    "source-changed": {
        "kind": "source-changed",
        "label": "Source snapshot changed during analysis",
        "detection": "Tree hash before and after scan differs.",
        "handling": "Abort the pass, keep the previous target bundle, and require a fresh snapshot import.",
        "recovery": "Re-run Scout on the new snapshot; never mix evidence from two source generations.",
    },
    "corrupt-file": {
        "kind": "corrupt-file",
        "label": "Corrupt or unreadable file",
        "detection": "UTF-8/read failure or unparseable XML/Gosu.",
        "handling": "List the file as quarantined with the parser error; continue scanning the rest.",
        "recovery": "Fix or exclude the file explicitly, then re-run the affected rule families.",
    },
    "duplicate-target": {
        "kind": "duplicate-target",
        "label": "Two patches write the same target path",
        "detection": "Duplicate target path in the Architect's patch list.",
        "handling": "Block the bundle before Guardian approval; keep the first patch and mark the second for review.",
        "recovery": "Split the change into separate packages or choose one owner.",
    },
    "analyzer-crash": {
        "kind": "analyzer-crash",
        "label": "Analyzer raises an unexpected exception",
        "detection": "Guarded scanner catches the exception and records the trace.",
        "handling": "Return a failed pass with the last good checkpoint; do not emit a green signal.",
        "recovery": "Re-run with a smaller file cap or quarantine the triggering file.",
    },
    "empty-snapshot": {
        "kind": "empty-snapshot",
        "label": "Snapshot has no supported source files",
        "detection": "Zero scanned files.",
        "handling": "Return an explicit insufficient-evidence state; do not fabricate findings or a score.",
        "recovery": "Confirm the archive layout and re-import.",
    },
}


class SourceChangedError(RuntimeError):
    """Raised when the source tree changes while a scan is in flight."""


class EmptySnapshotError(RuntimeError):
    """Raised when a scan has no supported files."""


@dataclass
class GuardedScan:
    scan: ScanResult | None
    status: str
    before_hash: str
    after_hash: str
    quarantine: list[dict[str, str]] = field(default_factory=list)
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "quarantine": self.quarantine,
            "error": self.error,
            "scan": None if self.scan is None else {
                "files_scanned": self.scan.files_scanned,
                "findings": len(self.scan.findings),
                "score": self.scan.score,
            },
        }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _event_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _append_resilience_event(audit: list[dict[str, Any]], *, agent: str, action: str,
                            object_id: str, reason: str | None = None) -> dict[str, Any]:
    previous = audit[-1]["hash"] if audit else "GENESIS"
    event = {
        "seq": len(audit),
        "ts": _now(),
        "agent": agent,
        "action": action,
        "object_id": object_id,
        "reason": reason,
        "prev_hash": previous,
    }
    event["hash"] = _event_hash(event)
    audit.append(event)
    return event


def _verify_chain(audit: list[dict[str, Any]]) -> bool:
    previous = "GENESIS"
    for index, event in enumerate(audit):
        payload = {key: value for key, value in event.items() if key != "hash"}
        if event.get("seq") != index or event.get("prev_hash") != previous:
            return False
        if event.get("hash") != _event_hash(payload):
            return False
        previous = event["hash"]
    return True


def guarded_scan(root: Path | str, *, apd_limit: int = 24,
                 rules_path: Path | str | None = None) -> GuardedScan:
    """Scan with source-immutability and failure containment.

    A changed source tree raises ``SourceChangedError`` through the returned
    error object rather than producing a mixed-generation green signal.
    """
    root = Path(root)
    before = _tree_hash(root)
    try:
        scan_kwargs: dict[str, Any] = {"apd_overrides": ()}
        if rules_path is not None:
            scan_kwargs["rules_path"] = rules_path
        scan = analyze_codebase(root, **scan_kwargs)
    except Exception as exc:
        after = _tree_hash(root)
        return GuardedScan(
            scan=None,
            status="analyzer_failed",
            before_hash=before,
            after_hash=after,
            error={"kind": "analyzer-crash", "type": type(exc).__name__, "message": str(exc)},
        )
    after = _tree_hash(root)
    if before != after:
        return GuardedScan(
            scan=None,
            status="source_changed",
            before_hash=before,
            after_hash=after,
            error={
                "kind": "source-changed",
                "message": "Source snapshot changed while the scan was running; refusing to mix generations.",
            },
        )
    quarantine = [
        {"path": item.get("path", ""), "reason": item.get("reason", "")}
        for item in scan.skipped if item.get("reason") and "excluded" not in item.get("reason", "")
    ]
    if scan.files_scanned == 0:
        return GuardedScan(
            scan=scan,
            status="insufficient_evidence",
            before_hash=before,
            after_hash=after,
            quarantine=quarantine,
            error={
                "kind": "empty-snapshot",
                "message": "No supported source files were scanned; no readiness score is claimed.",
            },
        )
    return GuardedScan(
        scan=scan,
        status="scanned",
        before_hash=before,
        after_hash=after,
        quarantine=quarantine,
    )


def _patches_for_scenario(result: dict[str, Any], scenario: dict[str, Any]) -> list[dict[str, Any]]:
    affected_rules = set(scenario.get("affected_rules", []))
    affected_paths = tuple(scenario.get("affected_paths", []))
    matched: list[dict[str, Any]] = []
    for patch in result.get("patches", []):
        target = str(patch.get("target_path", ""))
        if affected_rules.intersection(patch.get("rule_ids", [])) or (
            affected_paths and target.startswith(affected_paths)
        ):
            matched.append(patch)
    return matched


def _scenario_checks(result: dict[str, Any], scenario: dict[str, Any],
                     affected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenario_id = scenario["scenario_id"]
    checks: list[dict[str, Any]] = []
    if scenario_id == "GWCP-APD-NAMING-2027.04":
        overrides = result.get("overrides", {})
        too_long = [name for name in overrides.values() if len(name) > 20]
        checks.append({
            "name": "codegen overrides fit the 20-character limit",
            "ok": not too_long,
            "detail": f"{len(too_long)} override(s) exceed 20 characters" if too_long else "all overrides fit",
        })
        checks.append({
            "name": "APD patch cohort identified",
            "ok": bool(affected),
            "detail": f"{len(affected)} patch(es) require regeneration",
        })
    elif scenario_id == "GWCP-APP-EVENTS-V2-2027.04":
        configs = [patch for patch in affected if patch.get("target_path", "").startswith("config/appevents/")]
        checks.append({
            "name": "App Events contract is schema v2",
            "ok": False,
            "detail": f"{len(configs)} publication draft(s) still use the v1 envelope",
        })
    elif scenario_id == "GWCP-GATEWAY-MTLS-2027.04":
        checks.append({
            "name": "every route has mTLS and a scoped service identity",
            "ok": False,
            "detail": f"{len(affected)} route draft(s) only declare service-user auth",
        })
    elif scenario_id == "GWCP-GOSU-API-REMOVAL-2027.04":
        residual = [
            patch for patch in affected
            if any(rule in {"PF-CODE-API-001", "PF-CODE-API-002"} for rule in patch.get("rule_ids", []))
        ]
        checks.append({
            "name": "removed runtime API is absent from the target",
            "ok": False,
            "detail": f"{len(residual)} target draft(s) depend on a removed API family",
        })
    elif scenario_id == "GWCP-CLOUD-API-VERSION-2027.04":
        checks.append({
            "name": "Cloud API routes advertise the v2 prefix",
            "ok": False,
            "detail": f"{len(affected)} route draft(s) still advertise the v1 prefix",
        })
    else:
        checks.append({"name": "scenario recognized", "ok": False, "detail": "unknown scenario"})
    return checks


def evaluate_upgrade(result: dict[str, Any], scenario_id: str,
                     *, current_version: str | None = None) -> dict[str, Any]:
    """Evaluate a mid-migration release upgrade against a green draft."""
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise KeyError(f"unknown upgrade scenario: {scenario_id}")
    affected = _patches_for_scenario(result, scenario)
    checks = _scenario_checks(result, scenario, affected)
    failed = [check for check in checks if not check["ok"]]
    generation = int(result.get("generation", 1)) + 1
    green = bool(result.get("green_signal", {}).get("unified"))
    status = "revalidation_required" if failed else "compatible"
    event = {
        "event_id": f"UP-{generation:03d}",
        "ts": _now(),
        "kind": "core-release-upgrade",
        "scenario_id": scenario_id,
        "from_version": current_version or scenario["from_version"],
        "to_version": scenario["to_version"],
        "active_assessment_generation": result.get("generation", 1),
        "new_generation": generation,
        "affected_patches": [patch["patch_id"] for patch in affected],
        "affected_rules": sorted({rule for patch in affected for rule in patch.get("rule_ids", [])}),
        "invalidates_green": bool(green and failed),
        "status": status,
    }
    event["hash"] = _event_hash(event)
    return {
        "schema_version": "1.0",
        "status": status,
        "scenario": {
            "scenario_id": scenario_id,
            "label": scenario["label"],
            "from_version": scenario["from_version"],
            "to_version": scenario["to_version"],
            "severity": scenario["severity"],
            "description": scenario["description"],
        },
        "active_assessment_generation": result.get("generation", 1),
        "new_generation": generation,
        "green_signal_before": result.get("green_signal", {}),
        "green_signal_after": {
            "unified": (not failed) and bool(result.get("green_signal", {}).get("unified")),
            "reason": "stale after core release upgrade" if failed else "compatible; retain with revalidation",
            "guardian": False if failed else result.get("green_signal", {}).get("guardian", False),
            "critic": False if failed else result.get("green_signal", {}).get("critic", False),
            "planner": False if failed else result.get("green_signal", {}).get("planner", False),
        },
        "affected_patches": event["affected_patches"],
        "affected_rules": event["affected_rules"],
        "checks": checks,
        "required_actions": [
            {
                "action": scenario["required_action"],
                "owner": scenario["owner"],
                "severity": scenario["severity"],
                "rule_ids": scenario["affected_rules"],
            }
        ] if failed else [],
        "resume_options": _resume_options(scenario, failed),
        "event": event,
    }


def _resume_options(scenario: dict[str, Any], failed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not failed:
        return [{
            "option": "retain",
            "label": "Retain the green bundle with a revalidation note",
            "safe": True,
            "detail": "The upgrade does not touch this bundle's affected rules.",
        }]
    return [
        {
            "option": "revalidate",
            "label": "Re-run Architect with the new rule pack",
            "safe": True,
            "detail": scenario["required_action"],
            "recommended": True,
        },
        {
            "option": "rollback",
            "label": "Roll back to the last green checkpoint",
            "safe": True,
            "detail": "Keep the sealed bundle and resume after the release stabilizes.",
        },
        {
            "option": "defer",
            "label": "Defer the upgrade and pin the assessment release",
            "safe": True,
            "detail": "Record the risk owner and revisit before go-live.",
        },
    ]


def apply_upgrade_policy(result: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    """Return an updated result with the new generation and no stale green signal."""
    impact = evaluate_upgrade(result, scenario_id)
    updated = json.loads(json.dumps(result))
    updated["generation"] = impact["new_generation"]
    updated["green_signal"] = impact["green_signal_after"]
    if impact["status"] == "revalidation_required":
        updated["status"] = "revalidation_required"
    updated["upgrade"] = impact
    updated.setdefault("audit", [])
    _append_resilience_event(
        updated["audit"],
        agent="resilience",
        action="upgrade.detected",
        object_id=impact["event"]["event_id"],
        reason=f"{impact['scenario']['from_version']} → {impact['scenario']['to_version']}",
    )
    updated["audit_verified"] = _verify_chain(updated["audit"])
    updated["audit_detail"] = f"{len(updated['audit'])} events verified"
    return updated


def resume_assessment(result: dict[str, Any], impact: dict[str, Any],
                      choice: str) -> dict[str, Any]:
    """Record a reviewer's resume choice without approving the migration."""
    labels = {option["option"]: option["label"] for option in impact.get("resume_options", [])}
    if choice not in labels:
        raise ValueError(f"unknown resume option: {choice}")
    updated = json.loads(json.dumps(result))
    updated["generation"] = impact.get("new_generation", updated.get("generation", 1))
    updated["resume"] = {
        "choice": choice,
        "label": labels[choice],
        "recorded_at": _now(),
        "requires_human_approval": True,
    }
    if choice != "retain":
        updated["green_signal"] = {
            **updated.get("green_signal", {}),
            "unified": False,
            "reason": (
                f"Green signal cleared by review choice '{choice}'. "
                "Re-run the affected Architect pass before claiming green."
            ),
        }
    if choice == "revalidate":
        updated["status"] = "resume_requested"
    elif choice == "rollback":
        updated["status"] = "rolled_back_to_checkpoint"
    elif choice == "defer":
        updated["status"] = "upgrade_deferred"
    updated.setdefault("audit", [])
    _append_resilience_event(
        updated["audit"],
        agent="resilience",
        action=f"upgrade.resume.{choice}",
        object_id=impact.get("event", {}).get("event_id"),
        reason=labels[choice],
    )
    updated["audit_verified"] = _verify_chain(updated["audit"])
    updated["audit_detail"] = (
        f"{len(updated['audit'])} events verified"
        if updated["audit_verified"] else "audit chain verification failed"
    )
    return updated


def validate_patch_safety(patches: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Deterministic checks for duplicate or unsafe Architect targets."""
    issues: list[dict[str, str]] = []
    seen: set[str] = set()
    for patch in patches:
        target = str(patch.get("target_path", ""))
        if not target:
            issues.append({"kind": "missing-target", "patch_id": patch.get("patch_id", "?"),
                           "detail": "patch has no target path"})
            continue
        if target in seen:
            issues.append({"kind": "duplicate-target", "patch_id": patch.get("patch_id", "?"),
                           "detail": f"duplicate target {target}"})
        seen.add(target)
        if target.startswith("/") or ".." in Path(target).parts:
            issues.append({"kind": "unsafe-path", "patch_id": patch.get("patch_id", "?"),
                           "detail": f"unsafe target {target}"})
        if target.startswith("_gen/") or target == "_gen":
            issues.append({"kind": "gen-edit", "patch_id": patch.get("patch_id", "?"),
                           "detail": f"_gen target {target}"})
    return issues


def resilience_drills() -> list[dict[str, Any]]:
    """Expose the unexpected-scenario playbook to the UI and API."""
    return [
        {"scenario_id": key, **value}
        for key, value in UNEXPECTED_SCENARIOS.items()
    ]


def upgrade_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": value["scenario_id"],
            "label": value["label"],
            "from_version": value["from_version"],
            "to_version": value["to_version"],
            "severity": value["severity"],
            "affected_rules": value["affected_rules"],
        }
        for value in SCENARIOS.values()
    ]
