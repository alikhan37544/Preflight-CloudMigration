"""Five-agent cyclic code-migration loop.

Scout inventories the codebase. Architect generates target drafts. Guardian
deterministically re-scans the target and blocks while any cloud-breaking
pattern remains. Critic combines deterministic patch checks with architectural
risk review and either returns targeted fix requests or joins Guardian in a
green signal. Planner compiles the executive report.

The loop is intentionally bounded: at most ``max_iterations`` passes, no source
writes, no deployment, and no self-approval. Every patch remains ``pending``.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

from app.config import Settings
from app.models import CodeFinding
from app.services.case_studies import case_source_root, get_case_study
from app.services.codeanalyzer import (
    ScanResult,
    analyze_codebase,
    load_code_rules,
    scan_to_dict,
)
from app.services.parsers._xml import safe_parser
from app.services.refactor import apply_unified_diff, refactor_codebase
from app.services.resilience import (
    SCENARIOS,
    evaluate_upgrade,
    guarded_scan,
    validate_patch_safety,
)
from app.services.sarif import build_sarif, sarif_summary

BOUNDARY = (
    "Local, evidence-bound refactor drafts only. No source writes, no _gen edits, "
    "no deployment, and no self-approval. Every patch remains pending human review. "
    "Official Cloud Assurance was not run."
)

AGENTS: list[dict[str, str]] = [
    {
        "agent_id": "scout",
        "name": "Scout",
        "role": "Inventory and dependency map",
        "description": "Scans Gosu, Java plugins, XML metadata, integration configuration, and GUnit tests.",
    },
    {
        "agent_id": "architect",
        "name": "Architect",
        "role": "Refactor and patch generation",
        "description": "Generates target drafts, cloud configuration, unified diffs, and semantic-review notes.",
    },
    {
        "agent_id": "guardian",
        "name": "Guardian",
        "role": "Deterministic compliance gate",
        "description": "Re-scans the target for blockers, APD naming, secrets, path safety, and SARIF structure.",
    },
    {
        "agent_id": "critic",
        "name": "Critic",
        "role": "Hybrid adversarial review",
        "description": "Checks patch application and coverage, then records cross-application and runtime risks.",
    },
    {
        "agent_id": "planner",
        "name": "Planner",
        "role": "Executive migration report",
        "description": "Compiles the green signal, gates, patch inventory, and next actions into a reviewable report.",
    },
]

HIGH_RISK_RULES = {
    "PF-CODE-SQL-001", "PF-CODE-SQL-002", "PF-CODE-SQL-003",
    "PF-CODE-MSG-001", "PF-CODE-SRV-001", "PF-CODE-API-001",
    "PF-CODE-API-002", "PF-CODE-SEC-001", "PF-CODE-MT-001",
    "PF-CODE-MT-002",
}
RISK_LIBRARY: dict[str, dict[str, Any]] = {
    "data_access": {
        "severity": "high",
        "owner": "Data / rating owner",
        "action": "Run rating or data regression and compare outputs with the legacy path.",
        "title": "Semantic equivalence of the data-access rewrite",
    },
    "messaging": {
        "severity": "high",
        "owner": "Integration owner",
        "action": "Verify event contract, ordering key, delivery guarantee, and consumer acknowledgement.",
        "title": "App Events contract and delivery behaviour",
    },
    "servlet": {
        "severity": "high",
        "owner": "API product owner",
        "action": "Verify route contract, authentication scopes, and consumer cut-over.",
        "title": "Cloud API route replaces a servlet surface",
    },
    "security": {
        "severity": "high",
        "owner": "Security owner",
        "action": "Rotate the exposed credential and confirm the secret binding before go-live.",
        "title": "Credential rotation and secret binding",
    },
    "multitenancy": {
        "severity": "high",
        "owner": "Platform engineering",
        "action": "Run a tenant-isolation and concurrency test; confirm no request state leaks.",
        "title": "Tenant isolation after removing shared state",
    },
    "api": {
        "severity": "high",
        "owner": "Application development",
        "action": "Compile and regression-test the replaced public API path.",
        "title": "Public API replacement",
    },
    "apd": {
        "severity": "medium",
        "owner": "APD / product model owner",
        "action": "Regenerate endpoints and compile the target product model.",
        "title": "APD nameOverride and endpoint regeneration",
    },
    "transactions": {
        "severity": "medium",
        "owner": "Application development",
        "action": "Test bundle boundaries, rollback behaviour, and error propagation.",
        "title": "Transaction and failure-path behaviour",
    },
    "testing": {
        "severity": "medium",
        "owner": "QA engineering",
        "action": "Add a pure unit test for the extracted logic and an integration test for the database path.",
        "title": "Test coverage after removing database coupling",
    },
    "logging": {
        "severity": "medium",
        "owner": "Security / observability",
        "action": "Confirm redaction in logs and retain the audit trail required by policy.",
        "title": "Log redaction verification",
    },
    "crypto": {
        "severity": "high",
        "owner": "Security architecture",
        "action": "Validate the approved FIPS primitive and re-run encryption compatibility tests.",
        "title": "Cryptographic primitive migration",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _append_audit(audit: list[dict[str, Any]], *, agent: str, action: str,
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
    event["hash"] = _sha(_canonical(event))
    audit.append(event)
    return event


def verify_code_audit(audit: list[dict[str, Any]]) -> tuple[bool, str]:
    previous = "GENESIS"
    for index, event in enumerate(audit):
        payload = {key: value for key, value in event.items() if key != "hash"}
        if event.get("seq") != index:
            return False, f"event {index} has the wrong sequence"
        if event.get("prev_hash") != previous:
            return False, f"event {index} has a broken previous hash"
        if event.get("hash") != _sha(_canonical(payload)):
            return False, f"event {index} hash mismatch"
        previous = event["hash"]
    return True, f"{len(audit)} events verified"


def _rule_map() -> dict[str, dict[str, Any]]:
    return {rule["rule_id"]: rule for rule in load_code_rules()["rules"]}


def _feature_inventory(profile: dict[str, Any], scan: ScanResult) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for feature in profile.get("custom_features", []):
        evidence_paths = set(feature.get("evidence_paths", []))
        findings = [item for item in scan.findings if item.path in evidence_paths]
        features.append({
            "name": feature["name"],
            "owner": feature.get("owner", "unassigned"),
            "description": feature.get("description", ""),
            "evidence_paths": sorted(evidence_paths),
            "rule_ids": sorted({item.rule_id for item in findings}),
            "finding_count": len(findings),
            "status": "blocked" if any(item.severity.value == "error" for item in findings) else (
                "review" if findings else "clean"
            ),
            "cloud_target": feature.get("cloud_target", ""),
        })
    return features


def _import_edges(scan: ScanResult) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    pattern = re.compile(r"(?m)^\s*(?:uses|import)\s+([\w.]+)")
    for path, text in scan.source_texts.items():
        if not path.endswith((".gs", ".java")):
            continue
        for match in pattern.finditer(text):
            target = match.group(1)
            if target.startswith(("java.", "javax.", "jakarta.")):
                continue
            edges.append({"from": path, "to": target})
    return edges[:200]


def _scout_output(profile: dict[str, Any], scan: ScanResult,
                  guarded_status: str) -> dict[str, Any]:
    top = sorted(
        ({
            "path": path,
            "findings": len([item for item in scan.findings if item.path == path]),
        } for path in {item.path for item in scan.findings}),
        key=lambda item: (-item["findings"], item["path"]),
    )[:8]
    return {
        "status": "done",
        "summary": (
            f"{scan.files_scanned} source files · {scan.loc:,} LOC · "
            f"{len(scan.findings)} cloud blockers across {len(scan.by_category)} categories"
        ),
        "checks": [
            {"name": "source scan completed", "ok": guarded_status == "scanned",
             "detail": guarded_status},
            {"name": "supported files found", "ok": scan.files_scanned > 0,
             "detail": f"{scan.files_scanned} files"},
            {"name": "line evidence complete", "ok": all(item.line >= 1 for item in scan.findings),
             "detail": f"{len(scan.findings)} located findings"},
            {"name": "language coverage", "ok": bool(scan.by_language),
             "detail": ", ".join(f"{key}:{value}" for key, value in scan.by_language.items())},
        ],
        "files_scanned": scan.files_scanned,
        "loc": scan.loc,
        "by_language": scan.by_language,
        "by_category": scan.by_category,
        "by_severity": scan.by_severity,
        "features": _feature_inventory(profile, scan),
        "hotspots": top,
        "imports": _import_edges(scan),
        "skipped": scan.skipped[:20],
        "warnings": scan.warnings,
    }


def _parse_target_files(target_contents: dict[str, str]) -> tuple[bool, str]:
    """Validate syntax for structured target drafts; source code is not compiled."""
    failures: list[str] = []
    for path, content in sorted(target_contents.items()):
        suffix = Path(path).suffix.lower()
        try:
            if suffix == ".xml":
                etree.fromstring(content.encode("utf-8"), safe_parser())
            elif suffix == ".json":
                json.loads(content)
            elif suffix in {".yaml", ".yml"}:
                yaml.safe_load(content)
        except Exception as exc:
            failures.append(f"{path}: {type(exc).__name__}")
    return not failures, "; ".join(failures) or f"{len(target_contents)} structured file(s) parsed"


def _guardian_checks(source_scan: ScanResult, target_scan: ScanResult,
                     patches: list[dict[str, Any]], sarif: dict[str, Any],
                     target_contents: dict[str, str],
                     *, source_hash_unchanged: bool) -> list[dict[str, Any]]:
    patched_ids = {finding_id for patch in patches for finding_id in patch.get("finding_ids", [])}
    source_ids = {item.finding_id for item in source_scan.findings}
    safety = validate_patch_safety(patches)
    secret_patches = [
        patch for patch in patches
        if "PF-CODE-SEC-001" in patch.get("rule_ids", []) and patch.get("source_path")
    ]
    parse_ok, parse_detail = _parse_target_files(target_contents)
    sarif_run = (sarif.get("runs") or [{}])[0]
    checks = [
        {
            "name": "source snapshot unchanged",
            "ok": source_hash_unchanged,
            "detail": "before and after tree hashes match" if source_hash_unchanged else "source changed during scan",
        },
        {
            "name": "every source finding has a patch",
            "ok": source_ids <= patched_ids,
            "detail": f"{len(source_ids & patched_ids)}/{len(source_ids)} covered",
        },
        {
            "name": "target has no error-severity blockers",
            "ok": target_scan.errors == 0,
            "detail": f"{target_scan.errors} error finding(s)",
        },
        {
            "name": "target has no residual warnings",
            "ok": target_scan.warnings_count == 0,
            "detail": f"{target_scan.warnings_count} warning finding(s)",
        },
        {
            "name": "APD type names fit the effective import limit",
            "ok": not any(item.rule_id == "PF-CODE-APD-001" for item in target_scan.findings),
            "detail": f"{sum(1 for item in target_scan.findings if item.rule_id == 'PF-CODE-APD-001')} APD finding(s)",
        },
        {
            "name": "no _gen targets",
            "ok": not any(item["kind"] == "gen-edit" for item in safety),
            "detail": "target bundle only",
        },
        {
            "name": "target paths are unique and safe",
            "ok": not any(item["kind"] in {"duplicate-target", "unsafe-path", "missing-target"} for item in safety),
            "detail": f"{len(safety)} path issue(s)",
        },
        {
            "name": "generated structured drafts parse",
            "ok": parse_ok,
            "detail": parse_detail,
        },
        {
            "name": "secret patches are redacted",
            "ok": all(patch.get("diff_redacted") for patch in secret_patches),
            "detail": f"{sum(1 for patch in secret_patches if patch.get('diff_redacted'))}/{len(secret_patches)} redacted",
        },
        {
            "name": "all patches remain pending approval",
            "ok": all(patch.get("approval") == "pending" for patch in patches),
            "detail": f"{sum(1 for patch in patches if patch.get('approval') == 'pending')}/{len(patches)} pending",
        },
        {
            "name": "SARIF 2.1.0 is structurally valid",
            "ok": (
                sarif.get("version") == "2.1.0"
                and str(sarif.get("$schema", "")).endswith("sarif-2.1.0.json")
                and isinstance(sarif_run.get("tool", {}).get("driver", {}).get("rules"), list)
                and isinstance(sarif_run.get("results"), list)
            ),
            "detail": f"{len(sarif_run.get('results', []))} result(s), {len(sarif_run.get('tool', {}).get('driver', {}).get('rules', []))} rule(s)",
        },
        {
            "name": "SARIF results cover every source finding",
            "ok": len(sarif_run.get("results", [])) == len(source_scan.findings),
            "detail": f"{len(sarif_run.get('results', []))}/{len(source_scan.findings)}",
        },
        {
            "name": "target draft files exist",
            "ok": bool(patches),
            "detail": f"{len(patches)} patch(es)",
        },
    ]
    return checks


def _critic_checks(source_scan: ScanResult, target_scan: ScanResult,
                   patches: list[dict[str, Any]], *, guardian_green: bool,
                   source_hash_unchanged: bool, target_contents: dict[str, str]) -> list[dict[str, Any]]:
    patched_ids = {finding_id for patch in patches for finding_id in patch.get("finding_ids", [])}
    source_ids = {item.finding_id for item in source_scan.findings}
    apply_failures: list[str] = []
    for patch in patches:
        source_path = patch.get("source_path")
        if not source_path or patch.get("diff_redacted"):
            continue
        original = source_scan.source_texts.get(source_path, "")
        target_text = target_contents.get(patch["target_path"])
        if target_text is None:
            continue
        applied = apply_unified_diff(original, patch["diff"])
        if applied.rstrip("\n") != target_text.rstrip("\n"):
            apply_failures.append(patch["patch_id"])
    duplicate = len({patch["target_path"] for patch in patches}) != len(patches)
    checks = [
        {"name": "Guardian is green", "ok": guardian_green,
         "detail": "deterministic gate passed" if guardian_green else "deterministic gate is still blocking"},
        {"name": "patch coverage is complete", "ok": source_ids <= patched_ids,
         "detail": f"{len(source_ids & patched_ids)}/{len(source_ids)} findings patched"},
        {"name": "displayed diffs reproduce target drafts", "ok": not apply_failures,
         "detail": "all non-secret diffs apply cleanly" if not apply_failures else ", ".join(apply_failures)},
        {"name": "target paths are unique", "ok": not duplicate,
         "detail": f"{len({patch['target_path'] for patch in patches})} unique targets"},
        {"name": "source snapshot is unchanged", "ok": source_hash_unchanged,
         "detail": "read-only source contract held" if source_hash_unchanged else "source changed"},
        {"name": "target re-scan has zero blockers", "ok": target_scan.errors == 0 and target_scan.warnings_count == 0,
         "detail": f"{target_scan.errors} error / {target_scan.warnings_count} warning"},
        {"name": "no automatic approval", "ok": all(patch.get("approval") == "pending" for patch in patches),
         "detail": "every patch is pending"},
    ]
    return checks


def _critic_risks(source_scan: ScanResult) -> list[dict[str, Any]]:
    categories: dict[str, list[CodeFinding]] = {}
    for finding in source_scan.findings:
        categories.setdefault(finding.category, []).append(finding)
    risks: list[dict[str, Any]] = []
    for category, findings in sorted(categories.items()):
        template = RISK_LIBRARY.get(category)
        if template is None:
            continue
        risk_id = f"CR-{len(risks) + 1:02d}"
        risks.append({
            "risk_id": risk_id,
            "category": category,
            "severity": template["severity"],
            "title": template["title"],
            "owner": template["owner"],
            "action": template["action"],
            "rule_ids": sorted({item.rule_id for item in findings}),
            "evidence_paths": sorted({item.path for item in findings}),
            "blocking": False,
            "human_gate": True,
            "status": "open",
        })
    return risks


def _fix_requests(guardian: dict[str, Any], target_scan: ScanResult,
                  source_scan: ScanResult, patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    failed = [check for check in guardian["checks"] if not check["ok"]]
    if failed:
        requests.append({
            "request_id": "FR-01",
            "agent": "architect",
            "reason": "Guardian is not green",
            "instruction": "Resolve the failing deterministic checks before requesting green.",
            "items": [check["name"] for check in failed],
        })
    unpatched = sorted({
        finding.rule_id for finding in source_scan.findings
        if finding.finding_id not in {fid for patch in patches for fid in patch.get("finding_ids", [])}
    })
    if unpatched:
        requests.append({
            "request_id": f"FR-{len(requests) + 1:02d}",
            "agent": "architect",
            "reason": f"{target_scan.warnings_count + target_scan.errors} residual target finding(s)",
            "instruction": "Generate patches for every remaining error and warning; do not stop at errors.",
            "items": unpatched,
        })
    if target_scan.errors:
        requests.append({
            "request_id": f"FR-{len(requests) + 1:02d}",
            "agent": "architect",
            "reason": "documented blocker remains in the generated target",
            "instruction": "Remove the residual pattern and regenerate the target draft.",
            "items": sorted({item.rule_id for item in target_scan.findings if item.severity.value == "error"}),
        })
    return requests


def _guardian_output(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [check for check in checks if not check["ok"]]
    return {
        "verdict": "green" if not failed else "rework",
        "checks": checks,
        "blocking": [check["name"] for check in failed],
        "summary": (
            f"{len(checks) - len(failed)}/{len(checks)} deterministic checks passed"
            if failed else f"{len(checks)}/{len(checks)} deterministic checks passed"
        ),
    }


def _critic_output(checks: list[dict[str, Any]], risks: list[dict[str, Any]],
                   fix_requests: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [check for check in checks if not check["ok"]]
    green = not failed
    return {
        "verdict": "green" if green else "rework",
        "checks": checks,
        "residual_risks": risks,
        "fix_requests": fix_requests if not green else [],
        "summary": (
            f"{len(checks)}/{len(checks)} deterministic checks passed · "
            f"{len(risks)} human review gate(s)"
            if green else
            f"{len(checks) - len(failed)}/{len(checks)} checks passed · "
            f"{len(fix_requests)} fix request(s)"
        ),
    }


def _planner_report(profile: dict[str, Any], source_scan: ScanResult,
                    target_scan: ScanResult, patches: list[dict[str, Any]],
                    guardian: dict[str, Any], critic: dict[str, Any],
                    iterations: list[dict[str, Any]], green_signal: dict[str, Any],
                    sarif_info: dict[str, Any], upgrade: dict[str, Any] | None) -> dict[str, Any]:
    before = source_scan.score
    structural_after = target_scan.score
    gate_weight = sum(3 if risk["severity"] == "high" else 2 if risk["severity"] == "medium" else 1
                      for risk in critic["residual_risks"])
    adjusted = max(0, structural_after - gate_weight)
    summary = (
        f"{profile['name']} code-level migration: {len(source_scan.findings)} blockers "
        f"detected, {len(patches)} drafts generated, deterministic Guardian "
        f"{'green' if guardian['verdict'] == 'green' else 'still blocking'}, "
        f"Critic {'green' if critic['verdict'] == 'green' else 'requesting rework'}, "
        f"{len(critic['residual_risks'])} human review gate(s)."
    )
    if upgrade and upgrade.get("status") == "revalidation_required":
        summary += (
            f" A mid-migration upgrade to {upgrade['scenario']['to_version']} invalidated "
            "the green signal and requires revalidation."
        )
    next_actions = [
        f"{risk['risk_id']}: {risk['action']} (owner: {risk['owner']})"
        for risk in critic["residual_risks"]
    ]
    next_actions.extend(
        option["detail"] for option in (upgrade or {}).get("resume_options", [])
        if option.get("recommended")
    )
    markdown_lines = [
        f"# Codebase migration report — {profile['name']}",
        "",
        f"**Case:** `{profile['case_id']}` · **Segment:** {profile['segment']}  ",
        f"**Source:** {profile['source_release']} → **Target:** {profile['target_release']}  ",
        f"**Green signal:** `{'unified' if green_signal['unified'] else 'not green'}` · "
        f"**Human approval required:** `{green_signal['human_approval_required']}`  ",
        f"**Boundary:** {BOUNDARY}",
        "",
        "## Executive summary",
        "",
        summary,
        "",
        "## Cycle",
        "",
    ]
    for iteration in iterations:
        markdown_lines.append(
            f"- Iteration {iteration['iteration']}: Architect {iteration['architect']['status']} · "
            f"Guardian `{iteration['guardian']['verdict']}` · Critic `{iteration['critic']['verdict']}`"
        )
    markdown_lines += [
        "",
        "## Readiness",
        "",
        f"- Structural score before: **{before}/100**",
        f"- Structural score after: **{structural_after}/100**",
        f"- Human-gate-adjusted score: **{adjusted}/100**",
        f"- SARIF: {sarif_info['results']} results / {sarif_info['rules']} rules",
        "",
        "## Patch inventory",
        "",
        "| Patch | Target | Rules | Strategy | Approval |",
        "|---|---|---|---|---|",
    ]
    for patch in patches:
        markdown_lines.append(
            f"| {patch['patch_id']} | `{patch['target_path']}` | "
            f"{', '.join(patch['rule_ids'])} | {patch['strategy'][:110]} | {patch['approval']} |"
        )
    markdown_lines += ["", "## Human review gates", ""]
    for risk in critic["residual_risks"]:
        markdown_lines.append(
            f"- **{risk['risk_id']} · {risk['severity']} · {risk['title']}** — {risk['action']} "
            f"(owner: {risk['owner']}; rules: {', '.join(risk['rule_ids'])})"
        )
    if upgrade:
        markdown_lines += [
            "", "## Mid-migration upgrade", "",
            f"- Event: `{upgrade['event']['event_id']}` · "
            f"{upgrade['scenario']['from_version']} → {upgrade['scenario']['to_version']}",
            f"- Status: `{upgrade['status']}` · affected patches: {len(upgrade['affected_patches'])}",
        ]
        for check in upgrade["checks"]:
            markdown_lines.append(
                f"- **{'PASS' if check['ok'] else 'REWORK'}** {check['name']} — {check['detail']}"
            )
    markdown_lines += [
        "",
        "## Next actions",
        "",
    ] + [f"- {action}" for action in next_actions] + [
        "",
        "Every patch is a local draft. A human owner must review the semantic change, run the "
        "relevant regression, and approve it before any deployment. This report is not an "
        "official Cloud Assurance result.",
        "",
    ]
    report = "\n".join(markdown_lines)
    return {
        "executive_summary": summary,
        "readiness": {
            "score_before": before,
            "structural_score_after": structural_after,
            "human_gate_adjusted_score": adjusted,
            "score_caveat": (
                "Structural readiness is an advisory indicator from weighted findings, "
                "not a Cloud Assurance score."
            ),
        },
        "risk_register": critic["residual_risks"],
        "next_actions": next_actions,
        "report_markdown": report,
        "report_sha256": _sha(report),
        "sarif": sarif_info,
    }


def _empty_result(profile: dict[str, Any], message: str) -> dict[str, Any]:
    empty_scan = {
        "files_scanned": 0,
        "loc": 0,
        "findings": [],
        "by_language": {},
        "by_category": {},
        "by_severity": {},
        "snapshot_sha": "",
        "skipped": [],
    }
    return {
        "schema_version": "1.0",
        "case_id": profile["case_id"],
        "profile": profile,
        "mode": "five-agent cyclic · Scout → Architect ↔ Guardian/Critic → Planner",
        "boundary": BOUNDARY,
        "generated_at": _now(),
        "status": "insufficient_evidence",
        "generation": 1,
        "agents": [{**agent, "status": "done" if agent["agent_id"] == "scout" else "queued",
                    "summary": message} for agent in AGENTS],
        "iterations": [],
        "handoffs": [],
        "source_scan": empty_scan,
        "target_scan": {"files_scanned": 0, "findings": [], "by_severity": {},
                        "by_category": {}, "score": 0, "snapshot_sha": ""},
        "findings": [],
        "patches": [],
        "target_files": [],
        "added_files": [],
        "deleted_files": [],
        "overrides": {},
        "guardian": {"verdict": "rework", "checks": [], "blocking": [], "summary": message},
        "critic": {"verdict": "rework", "checks": [], "residual_risks": [],
                    "fix_requests": [], "summary": message},
        "green_signal": {
            "unified": False, "guardian": False, "critic": False, "planner": False,
            "human_approval_required": True, "gates": 0,
            "reason": message,
        },
        "planner": {
            "executive_summary": message,
            "readiness": {
                "score_before": 0, "structural_score_after": 0,
                "human_gate_adjusted_score": 0,
                "score_caveat": "No score is claimed for an insufficient-evidence snapshot.",
            },
            "risk_register": [],
            "next_actions": ["Confirm the archive layout and re-import the source snapshot."],
            "report_markdown": f"# Codebase migration report\n\n{message}\n",
            "report_sha256": _sha(message),
            "sarif": {"version": "2.1.0", "rules": 0, "results": 0, "errors": 0, "warnings": 0},
        },
        "sarif": {
            "summary": {"version": "2.1.0", "rules": 0, "results": 0, "errors": 0, "warnings": 0},
            "path": "",
            "json": {},
        },
        "audit": [],
        "audit_verified": True,
        "audit_detail": "0 events verified",
        "error": {"kind": "insufficient-evidence", "message": message},
    }


def run_code_migration(case_id: str, settings: Settings, *,
                       max_iterations: int = 3,
                       upgrade_scenario: str | None = None) -> dict[str, Any]:
    """Run the bounded five-agent cycle over one case-study fixture."""
    started = time.monotonic()
    profile = get_case_study(case_id)
    root = case_source_root(settings, case_id)
    guarded = guarded_scan(root)
    if guarded.scan is None:
        result = _empty_result(profile, (guarded.error or {}).get("message", "scan failed"))
        result["resilience"] = guarded.to_dict()
        return result
    if guarded.scan.files_scanned == 0:
        result = _empty_result(profile, (guarded.error or {}).get("message", "empty snapshot"))
        result["resilience"] = guarded.to_dict()
        return result

    source_scan = guarded.scan
    rules = _rule_map()
    scenario = SCENARIOS.get(upgrade_scenario) if upgrade_scenario else None
    effective_apd_limit = int(
        (scenario or {}).get("effective", {}).get("apd_name_limit", 24)
    )
    audit: list[dict[str, Any]] = []
    iterations: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    sarif = build_sarif(source_scan.findings, run_label=case_id, rules=list(rules.values()))
    sarif_info = sarif_summary(sarif)

    _append_audit(audit, agent="orchestrator", action="code-migration.started",
                  object_id=case_id, reason=f"bounded cyclic loop · max_iterations={max_iterations}")
    scout = _scout_output(profile, source_scan, guarded.status)
    _append_audit(audit, agent="scout", action="agent.completed", object_id="scout",
                  reason=scout["summary"])
    handoffs.append({
        "seq": len(handoffs) + 1,
        "from": "scout",
        "to": "architect",
        "kind": "handoff",
        "message": (
            f"Scout handed over {source_scan.files_scanned} files, "
            f"{len(source_scan.findings)} evidence-linked blockers, and "
            f"{len(scout['features'])} custom feature slices."
        ),
    })

    final_refactor = None
    target_scan: ScanResult | None = None
    final_guardian: dict[str, Any] = {"verdict": "rework", "checks": [], "blocking": [], "summary": ""}
    final_critic: dict[str, Any] = {
        "verdict": "rework", "checks": [], "residual_risks": [], "fix_requests": [], "summary": "",
    }

    try:
        for iteration_no in range(1, max(1, max_iterations) + 1):
            mode = "error-first" if iteration_no == 1 else "full"
            severities = {"error"} if iteration_no == 1 else {"error", "warning"}
            _append_audit(audit, agent="architect", action=f"iteration.{iteration_no}.started",
                          object_id="architect", reason=f"mode={mode}")
            refactor = refactor_codebase(
                source_scan, source_root=root, address_severities=severities,
                apd_limit=effective_apd_limit,
            )
            try:
                target_scan = analyze_codebase(refactor.target_root)
            except Exception as exc:
                refactor.cleanup()
                raise RuntimeError(f"Guardian target re-scan failed: {type(exc).__name__}: {exc}") from exc
            target_contents = {
                path.relative_to(refactor.target_root).as_posix(): path.read_text(encoding="utf-8", errors="replace")
                for path in refactor.target_root.rglob("*") if path.is_file()
            }
            architect_summary = {
                "status": "done",
                "mode": mode,
                "patches": len(refactor.patches),
                "target_files": len(target_contents),
                "added_files": len(refactor.added_files),
                "deleted_files": len(refactor.deleted_files),
                "summary": (
                    f"{len(refactor.patches)} patch(es) · {len(target_contents)} target file(s) · "
                    f"{len(refactor.added_files)} cloud config draft(s)"
                ),
            }
            _append_audit(audit, agent="architect", action=f"iteration.{iteration_no}.completed",
                          object_id="architect", reason=architect_summary["summary"])
            handoffs.append({
                "seq": len(handoffs) + 1,
                "from": "architect",
                "to": "guardian",
                "kind": "handoff",
                "message": (
                    f"Architect pass {iteration_no} ({mode}) produced {len(refactor.patches)} patch(es) "
                    f"and {len(refactor.added_files)} supporting cloud config draft(s)."
                ),
            })

            _append_audit(audit, agent="guardian", action=f"iteration.{iteration_no}.started",
                          object_id="guardian")
            guardian_checks = _guardian_checks(
                source_scan, target_scan, refactor.patches, sarif,
                target_contents,
                source_hash_unchanged=guarded.before_hash == guarded.after_hash,
            )
            guardian = _guardian_output(guardian_checks)
            _append_audit(audit, agent="guardian", action=f"iteration.{iteration_no}.completed",
                          object_id="guardian", reason=guardian["summary"])
            handoffs.append({
                "seq": len(handoffs) + 1,
                "from": "guardian",
                "to": "critic",
                "kind": "gate",
                "message": (
                    f"Guardian verdict {guardian['verdict']} · "
                    f"{guardian['summary']}"
                    + (f" · blocking: {', '.join(guardian['blocking'])}" if guardian["blocking"] else "")
                ),
            })

            _append_audit(audit, agent="critic", action=f"iteration.{iteration_no}.started",
                          object_id="critic")
            critic_checks = _critic_checks(
                source_scan, target_scan, refactor.patches,
                guardian_green=guardian["verdict"] == "green",
                source_hash_unchanged=guarded.before_hash == guarded.after_hash,
                target_contents=target_contents,
            )
            risks = _critic_risks(source_scan)
            fix_requests = _fix_requests(guardian, target_scan, source_scan, refactor.patches)
            critic = _critic_output(critic_checks, risks, fix_requests)
            _append_audit(audit, agent="critic", action=f"iteration.{iteration_no}.completed",
                          object_id="critic", reason=critic["summary"])

            iteration = {
                "iteration": iteration_no,
                "architect": architect_summary,
                "guardian": guardian,
                "critic": critic,
                "target": {
                    "findings": len(target_scan.findings),
                    "by_severity": target_scan.by_severity,
                    "score": target_scan.score,
                },
                "decision": "green" if guardian["verdict"] == "green" and critic["verdict"] == "green" else "rework",
            }
            iterations.append(iteration)
            final_refactor = refactor
            final_guardian = guardian
            final_critic = critic

            if iteration["decision"] == "green":
                handoffs.append({
                    "seq": len(handoffs) + 1,
                    "from": "critic",
                    "to": "planner",
                    "kind": "green",
                    "message": (
                        "Guardian and Critic both green. Planner may compile the executive report; "
                        "human review gates remain open."
                    ),
                })
                break

            handoffs.append({
                "seq": len(handoffs) + 1,
                "from": "critic",
                "to": "architect",
                "kind": "rework",
                "message": (
                    f"Critic requested {len(fix_requests)} targeted fix request(s). "
                    "Architect re-enters the loop; the prior draft is superseded."
                ),
            })
            if iteration_no < max_iterations:
                refactor.cleanup()

        if final_refactor is None or target_scan is None:
            raise RuntimeError("no Architect pass completed")

        target_contents = {
            path.relative_to(final_refactor.target_root).as_posix(): path.read_text(
                encoding="utf-8", errors="replace"
            )
            for path in final_refactor.target_root.rglob("*") if path.is_file()
        }
        target_files = [
            {
                "path": path,
                "sha256": _sha(content),
                "bytes": len(content.encode("utf-8")),
                "content": content,
            }
            for path, content in sorted(target_contents.items())
        ]

        green = final_guardian["verdict"] == "green" and final_critic["verdict"] == "green"
        green_signal = {
            "unified": green,
            "guardian": final_guardian["verdict"] == "green",
            "critic": final_critic["verdict"] == "green",
            "planner": True,
            "human_approval_required": True,
            "gates": len(final_critic["residual_risks"]),
            "reason": (
                "Guardian and Critic both green; Planner compiled the report. "
                "Every patch remains pending human approval."
                if green else
                "The loop exhausted its iteration budget before both gates were green."
            ),
        }
        planner = _planner_report(
            profile, source_scan, target_scan, final_refactor.patches,
            final_guardian, final_critic, iterations, green_signal,
            sarif_info, None,
        )
        _append_audit(audit, agent="planner", action="report.compiled",
                      object_id="planner", reason=planner["report_sha256"][:16])

        result: dict[str, Any] = {
            "schema_version": "1.0",
            "case_id": case_id,
            "profile": profile,
            "mode": "five-agent cyclic · Scout → Architect ↔ Guardian/Critic → Planner",
            "boundary": BOUNDARY,
            "generated_at": _now(),
            "duration_ms": int((time.monotonic() - started) * 1000),
            "generation": 1,
            "status": "green_with_human_gates" if green else "blocked",
            "agents": [
                {"agent": agent["agent_id"], "name": agent["name"], "role": agent["role"],
                 "description": agent["description"], "status": "done" if green else (
                     "failed" if agent["agent_id"] == "critic" else "done"
                 ), "summary": (
                     scout["summary"] if agent["agent_id"] == "scout" else
                     iterations[-1]["architect"]["summary"] if agent["agent_id"] == "architect" else
                     final_guardian["summary"] if agent["agent_id"] == "guardian" else
                     final_critic["summary"] if agent["agent_id"] == "critic" else
                     "Executive report compiled; human approval remains required."
                 )}
                for agent in AGENTS
            ],
            "scout": scout,
            "iterations": iterations,
            "handoffs": handoffs,
            "source_scan": scan_to_dict(source_scan),
            "target_scan": {
                "files_scanned": target_scan.files_scanned,
                "findings": [item.model_dump(mode="json") for item in target_scan.findings],
                "by_severity": target_scan.by_severity,
                "by_category": target_scan.by_category,
                "score": target_scan.score,
                "snapshot_sha": target_scan.snapshot_sha,
            },
            "findings": [item.model_dump(mode="json") for item in source_scan.findings],
            "patches": final_refactor.patches,
            "target_files": target_files,
            "added_files": final_refactor.added_files,
            "deleted_files": final_refactor.deleted_files,
            "overrides": final_refactor.overrides,
            "guardian": final_guardian,
            "critic": final_critic,
            "planner": planner,
            "green_signal": green_signal,
            "sarif": {
                "summary": sarif_info,
                "path": f"code-migration/{case_id}.sarif",
                "json": sarif,
            },
            "resilience": guarded.to_dict(),
            "audit": audit,
        }
        if upgrade_scenario:
            result["upgrade"] = evaluate_upgrade(result, upgrade_scenario)
            if result["upgrade"]["status"] == "revalidation_required":
                result["status"] = "revalidation_required"
                result["green_signal"].update({
                    "unified": False,
                    "guardian": False,
                    "critic": False,
                    "reason": (
                        "A mid-migration core release upgrade invalidated the green signal; "
                        "re-run the Architect with the new rule pack."
                    ),
                })
                _append_audit(audit, agent="resilience", action="upgrade.invalidated-green",
                              object_id=result["upgrade"]["event"]["event_id"],
                              reason=result["upgrade"]["scenario"]["to_version"])
        verified, detail = verify_code_audit(audit)
        result["audit_verified"] = verified
        result["audit_detail"] = detail
        return result
    except KeyError:
        raise
    except Exception as exc:
        failure = _empty_result(profile, f"Agent pass failed: {type(exc).__name__}: {exc}")
        failure["status"] = "failed"
        failure["source_scan"] = scan_to_dict(source_scan)
        failure["iterations"] = iterations
        failure["handoffs"] = handoffs
        failure["audit"] = audit
        failure["audit_verified"] = verify_code_audit(audit)[0]
        failure["audit_detail"] = verify_code_audit(audit)[1]
        return failure
    finally:
        if final_refactor is not None:
            final_refactor.cleanup()


def code_migration_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Compact summary for API lists and the case-study page."""
    return {
        "case_id": result.get("case_id"),
        "status": result.get("status"),
        "green": bool(result.get("green_signal", {}).get("unified")),
        "findings": len(result.get("findings", [])),
        "patches": len(result.get("patches", [])),
        "iterations": len(result.get("iterations", [])),
        "gates": len(result.get("critic", {}).get("residual_risks", [])),
        "score_before": result.get("planner", {}).get("readiness", {}).get("score_before"),
        "score_after": result.get("planner", {}).get("readiness", {}).get("human_gate_adjusted_score"),
        "audit_verified": result.get("audit_verified"),
    }
