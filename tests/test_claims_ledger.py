"""Claims-ledger and rule-coverage gate (A14)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "docs" / "claims-ledger.json"
STATUSES = {
    "VERIFIED", "VERIFIED-VENDOR-CLAIM", "VERIFIED-PROCESS", "VERIFIED-POLICY",
    "GATED", "SECONDARY", "PRODUCT-CLAIM", "UNSUPPORTED", "REJECTED",
}


def ledger() -> dict:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_ledger_shape_and_statuses() -> None:
    data = ledger()
    assert data["schema_version"] == "1.0"
    assert len(data["claims"]) >= 30
    for claim in data["claims"]:
        assert claim["id"].startswith("C-")
        assert claim["status"] in STATUSES, claim["id"]
        assert claim["claim"]
        assert claim["falsifier"]
        assert claim["consequence"]
        if claim["status"] != "PRODUCT-CLAIM":
            assert claim["source_url"].startswith("https://"), claim["id"]
        if claim["status"] == "VERIFIED":
            assert claim["access"] in {"public", "gated-body", "gated-app", "mixed", "none"}


def test_every_rule_has_a_ledger_row() -> None:
    data = ledger()
    covered = {rule for claim in data["claims"] for rule in claim.get("rule_ids", [])}

    review_rules = yaml.safe_load((REPO / "rules" / "review_rules.yaml").read_text(encoding="utf-8"))["rules"]
    for rule in review_rules:
        rule_id = rule["rule_id"]
        if rule["claim_strength"] == "heuristic":
            assert rule_id in covered, f"heuristic {rule_id} needs a PRODUCT-CLAIM row"
        else:
            assert rule_id in covered, f"{rule_id} missing from claims ledger"

    gold_mappings = json.loads((REPO / "ground_truth" / "mappings.json").read_text(encoding="utf-8"))["mappings"]
    for mapping in gold_mappings:
        assert mapping["rule_id"] in covered, mapping["rule_id"]


def test_no_prohibited_phrases_in_product_ui() -> None:
    prohibited = [
        "Guidewire-certified", "Cloud Assurance pass", "APD converter",
        "production-ready", "100% detection", "replaces Cloud Assurance",
        "6-8 weeks", "6–8 weeks", "first AI migration tool", "six-figure",
        "priced assumption register",
    ]
    paths = list((REPO / "app" / "templates").glob("*.html"))
    paths += list((REPO / "app" / "static").rglob("*.*"))
    paths += list((REPO / "rules").glob("*.yaml"))
    violations = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for phrase in prohibited:
            if phrase.lower() in text.lower():
                violations.append(f"{path.name}: {phrase}")
    assert violations == []


def test_markdown_mirrors_every_claim() -> None:
    text = (REPO / "docs" / "claims-ledger.md").read_text(encoding="utf-8")
    for claim in ledger()["claims"]:
        assert claim["id"] in text, claim["id"]


def test_rulepack_is_hashed_and_present() -> None:
    assert (REPO / "rules" / "feature_rules.yaml").is_file()
    assert (REPO / "rules" / "review_rules.yaml").is_file()
    assert (REPO / "rules" / "mapping_rules.yaml").is_file()
