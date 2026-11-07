"""Claims-ledger lint: statuses, URLs, rule coverage, prohibited phrases."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "docs" / "claims-ledger.json"
STATUSES = {
    "VERIFIED", "VERIFIED-VENDOR-CLAIM", "VERIFIED-PROCESS", "VERIFIED-POLICY",
    "GATED", "SECONDARY", "PRODUCT-CLAIM", "UNSUPPORTED", "REJECTED",
}
PROHIBITED = [
    "Guidewire-certified", "Cloud Assurance pass", "APD converter",
    "production-ready", "100% detection", "replaces Cloud Assurance",
    "6-8 weeks", "6–8 weeks", "first AI migration tool", "six-figure",
    "priced assumption register",
]


def lint_ledger() -> list[str]:
    issues: list[str] = []
    if not LEDGER.is_file():
        return ["docs/claims-ledger.json is missing"]
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        issues.append("ledger schema_version must be 1.0")
    claims = data.get("claims", [])
    if len(claims) < 30:
        issues.append(f"ledger has only {len(claims)} claims")

    covered: set[str] = set()
    for claim in claims:
        cid = claim.get("id", "?")
        for field in ["claim", "falsifier", "consequence"]:
            if not claim.get(field):
                issues.append(f"{cid}: missing {field}")
        if claim.get("status") not in STATUSES:
            issues.append(f"{cid}: invalid status {claim.get('status')!r}")
        if claim.get("status") != "PRODUCT-CLAIM":
            if not str(claim.get("source_url", "")).startswith("https://"):
                issues.append(f"{cid}: non-product claim needs an https source_url")
        covered.update(claim.get("rule_ids", []))

    review_rules = yaml.safe_load((REPO / "rules" / "review_rules.yaml").read_text(encoding="utf-8"))["rules"]
    for rule in review_rules:
        if rule["rule_id"] not in covered:
            issues.append(f"rule {rule['rule_id']} has no claims-ledger row")

    gold = json.loads((REPO / "ground_truth" / "mappings.json").read_text(encoding="utf-8"))["mappings"]
    for mapping in gold:
        if mapping["rule_id"] not in covered:
            issues.append(f"mapping rule {mapping['rule_id']} has no claims-ledger row")

    for path in list((REPO / "app" / "templates").glob("*.html")) + list((REPO / "app" / "static").rglob("*.*")) + list((REPO / "rules").glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        for phrase in PROHIBITED:
            if phrase.lower() in text.lower():
                issues.append(f"{path.name}: prohibited phrase {phrase!r}")

    return issues


def main() -> int:
    issues = lint_ledger()
    if issues:
        print("claims-lint: FAIL")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("claims-lint: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
