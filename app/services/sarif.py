"""SARIF 2.1.0 export for code-level cloud-blocker findings.

The export is intentionally conservative: it carries rule metadata, a line
location, a stable fingerprint, the evidence id, and remediation guidance. It
does not embed source excerpts, secret values, or tenant data. A GitHub Action
can upload this file with ``upload-sarif`` without the repository shipping a
custom converter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from app.models import CodeFinding

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SARIF_VERSION = "2.1.0"
TOOL_NAME = "PreFlight CodeGuard"
TOOL_VERSION = "1.0.0"

_LEVEL = {"error": "error", "warning": "warning", "note": "note", "info": "note"}


def _short(text: str, limit: int = 160) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_sarif(findings: Iterable[CodeFinding], *, run_label: str = "synthetic-estate",
                rules: list[dict[str, Any]] | None = None,
                tool_version: str = TOOL_VERSION) -> dict[str, Any]:
    findings = list(findings)
    rules_by_id = {rule["rule_id"]: rule for rule in (rules or [])}
    rule_index: dict[str, int] = {}
    sarif_rules: list[dict[str, Any]] = []
    for finding in findings:
        if finding.rule_id in rule_index:
            continue
        rule_index[finding.rule_id] = len(sarif_rules)
        pack_rule = rules_by_id.get(finding.rule_id, {})
        sarif_rules.append({
            "id": finding.rule_id,
            "name": _short(finding.title, 80).replace(" ", ""),
            "shortDescription": {"text": finding.title},
            "fullDescription": {
                "text": pack_rule.get("message") or finding.message or finding.title
            },
            "helpUri": finding.standard_url or pack_rule.get("standard_url") or "",
            "help": {
                "text": (
                    f"{finding.remediation or pack_rule.get('remediation', '')}\n\n"
                    f"Cloud target: {finding.cloud_target or pack_rule.get('cloud_target', 'review required')}\n"
                    "Claim strength: "
                    f"{finding.claim_strength.value}. Advisory static analysis; not an official "
                    "Cloud Assurance assessment."
                ).strip()
            },
            "defaultConfiguration": {
                "level": _LEVEL.get(finding.severity.value, "warning")
            },
            "properties": {
                "category": finding.category,
                "claim_strength": finding.claim_strength.value,
                "standard_family": finding.standard_family.value,
                "standard_id": finding.standard_id,
                "cloud_target": finding.cloud_target,
                "autofix": finding.autofix,
                "tags": ["guidewire-cloud", "code-migration", finding.category],
            },
        })

    results: list[dict[str, Any]] = []
    for finding in findings:
        results.append({
            "ruleId": finding.rule_id,
            "ruleIndex": rule_index[finding.rule_id],
            "level": _LEVEL.get(finding.severity.value, "warning"),
            "message": {"text": finding.message},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": finding.path,
                        "uriBaseId": "%SRCROOT%",
                    },
                    "region": {
                        "startLine": finding.line,
                        "startColumn": finding.column,
                    },
                }
            }],
            "partialFingerprints": {
                "primaryLocationLineHash": f"{finding.fingerprint}:1",
                "preflightFindingId": finding.finding_id,
            },
            "properties": {
                "finding_id": finding.finding_id,
                "evidence_sha": finding.excerpt_sha,
                "claim_strength": finding.claim_strength.value,
                "standard_id": finding.standard_id,
                "standard_url": finding.standard_url,
                "cloud_target": finding.cloud_target,
                "remediation": finding.remediation,
                "redacted": finding.redacted,
                "synthetic": True,
            },
        })

    return {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {
                "driver": {
                    "name": TOOL_NAME,
                    "version": tool_version,
                    "semanticVersion": tool_version,
                    "informationUri": "https://github.com/SaundaryaSingh/Preflight-CloudMigration",
                    "rules": sarif_rules,
                }
            },
            "automationDetails": {
                "id": f"preflight/codebase/{run_label}",
                "description": {
                    "text": "PreFlight code-level cloud-blocker review (advisory, offline, synthetic fixtures)"
                },
            },
            "invocations": [{
                "executionSuccessful": True,
                "toolExecutionNotifications": [],
                "properties": {
                    "run_label": run_label,
                    "official_cloud_assurance": False,
                    "boundary": "Advisory static analysis only; every refactor remains pending human approval.",
                },
            }],
            "results": results,
            "properties": {
                "preflight_schema": "codebase-migration/1.0",
                "official_cloud_assurance": False,
                "synthetic": True,
                "result_count": len(results),
                "rule_count": len(sarif_rules),
                "error_count": sum(1 for item in findings if item.severity.value == "error"),
                "warning_count": sum(1 for item in findings if item.severity.value == "warning"),
            },
        }],
    }


def sarif_json(sarif: dict[str, Any]) -> str:
    return json.dumps(sarif, indent=2, ensure_ascii=False) + "\n"


def write_sarif(path: Path | str, sarif: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sarif_json(sarif), encoding="utf-8")
    return path


def sarif_summary(sarif: dict[str, Any]) -> dict[str, Any]:
    run = (sarif.get("runs") or [{}])[0]
    results = run.get("results", [])
    driver = run.get("tool", {}).get("driver", {})
    return {
        "version": sarif.get("version"),
        "schema": sarif.get("$schema"),
        "tool": driver.get("name"),
        "rules": len(driver.get("rules", [])),
        "results": len(results),
        "errors": sum(1 for item in results if item.get("level") == "error"),
        "warnings": sum(1 for item in results if item.get("level") == "warning"),
        "uris": sorted({result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
                        for result in results if result.get("locations")}),
    }
